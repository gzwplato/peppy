# peppy Copyright (c) 2006-2008 Rob McMullen
# Licenced under the GPLv2; see http://peppy.flipturn.org for more info
"""Reading and writing raw HSI cubes.

This class supports reading HSI data cubes (that are stored in raw,
uncompressed formats) using memory mapped file access.
"""

import os,sys,re,random, glob
from cStringIO import StringIO
from datetime import datetime

import numpy
import utils

import peppy.vfs as vfs

from peppy.debug import *


# ENVI standard byte order: 0=little endian, 1=big endian
LittleEndian=0
BigEndian=1
if sys.byteorder=='little':
    nativeByteOrder=LittleEndian
else:
    nativeByteOrder=BigEndian
byteordertext=['<','>']


class MetadataMixin(debugmixin):
    """Generic mixin interface for Cube metadata.

    This will be subclassed by various formats like ENVI and GDAL to
    load the metadata from files and to provide a method to load the
    cube data.
    """

    format_name="unknown"
    extensions=[]

    @classmethod
    def identify(cls, fh, filename=None):
        """Scan through the file-like object to identify if it is a
        valid instance of the type that the subclass is expecting to
        load."""
        return False
    
    @classmethod
    def canExport(cls):
        return False
    
    @classmethod
    def export(cls, fh, cube, options, url):
        """Create a new file with the given cube.
        
        @param fh: file-like object to which the data should be written
        @param cube: HSI.Cube object to be saved
        @param options: dict containing name value pairs that can override the cube data to provide for data conversion on output (e.g. change the interleave from BIP to BIL)
        @param url: url of the file-like object
        """
        pass

    def formatName(self):
        return self.format_name

    def fileExtensions(self):
        return self.extensions
    
    def open(self,filename=None):
        pass

    def save(self,filename=None):
        pass
    
    def getCube(self,filename=None,index=None):
        """Return a cube instance that represents the data pointed to
        by the metadata."""
        return None

    def getCubeNames(self):
        """Return names of cubes contained within this file.

        Return a list of names that identify the cubes contained
        within this file.
        """
        return []

    def getNumCubes(self):
        return len(self.getCubeNames())
    
    def __str__(self):
        fs=StringIO()
        order=self.keys()
        if self.debug: dprint("keys in object: %s" % order)
        order.sort()
        for key in order:
            val=self[key]
            fs.write("%s = %s%s" % (key,val,os.linesep))
        return fs.getvalue()


class CubeReader(debugmixin):
    """Abstract class for reading raw data from an HSI cube"""
    def save(self, url):
        """Save the data to another file"""
        raise NotImplementedError
        
    def getPixel(self, line, sample, band):
        """Get a single pixel value"""
        raise NotImplementedError

    def getBandRaw(self, band):
        """Get an array of (lines x samples) at the specified band"""
        raise NotImplementedError

    def getSpectraRaw(self, line, sample):
        """Get the spectra at the given pixel"""
        raise NotImplementedError

    def getFocalPlaneRaw(self, line):
        """Get an array of (bands x samples) the given line"""
        raise NotImplementedError

    def getFocalPlaneDepthRaw(self, sample, band):
        """Get an array of values at constant line, the given sample and band"""
        raise NotImplementedError

    def getLineOfSpectraCopy(self, line):
        """Get the spectra along the given line"""
        raise NotImplementedError

    def locationToFlat(self,line,sample,band):
        """Convert location (line,sample,band) to flat index"""
        raise NotImplementedError


class FileCubeReader(CubeReader):
    """Base class for direct file access to data cube.
    
    Note: this is (potentially much) slower than mmap access of the
    L{MMapCubeReader}, but won't throw out of memory exceptions.
    """
    def __init__(self, cube, url=None, array=None):
        self.fh = vfs.open(url)
        self.offset = cube.data_offset


class MMapCubeReader(CubeReader):
    """Base class for memory mapped access to data cube using numpy's built-in
    mmap function.
    
    Note: this can fail with MemoryError (or WindowsError on MSW) when
    attempting to first mmap a file that is larger than physical memory.
    """
    def __init__(self, cube, url=None, array=None):
        self.mmap = None
        self.raw = None
        self.lines = cube.lines
        self.samples = cube.samples
        self.bands = cube.bands
        if url:
            self.open(cube, url)
        elif array:
            self.raw = array
        
        if self.raw is not None:
            self.shape(cube)
    
#    def __str__(self):
#        return repr(self.raw)
    
    def open(self, cube, url):
        if url.scheme == "file":
            self.mmap = numpy.memmap(str(url.path), mode="r")
        elif url.scheme == "mem":
            fh = vfs.open(url)
            data = fh.read()
            self.mmap = numpy.fromstring(data, dtype=numpy.uint8)
        else:
            self.mmap = vfs.open_numpy_mmap(url)
        
        if cube.data_offset>0:
            if cube.data_bytes>0:
                slice = self.mmap[cube.data_offset:cube.data_offset+cube.data_bytes]
            else:
                slice = self.mmap[cube.data_offset:]
        else:
            slice = self.mmap[:]
                
        view = slice.view(cube.data_type)
        self.raw = view.newbyteorder(byteordertext[cube.byte_order])
    
    def save(self, url):
        if self.mmap:
            self.mmap.flush()
            self.mmap.sync()
        else:
            self.raw.tofile(str(url))
    
    def shape(self, cube):
        """Shape the memory mapped to the correct data type and offset within
        the file."""
        raise NotImplementedError


class MMapBIPCubeReader(MMapCubeReader):
    def shape(self, cube):
        self.raw = numpy.reshape(self.raw, (cube.lines, cube.samples, cube.bands))

    def getPixel(self, line, sample, band):
        return self.raw[line][sample][band]

    def getBandRaw(self, band):
        """Get an array of (lines x samples) at the specified band"""
        s = self.raw[:, :, band]
        return s

    def getSpectraRaw(self, line, sample):
        """Get the spectra at the given pixel"""
        s = self.raw[line, sample, :]
        return s

    def getFocalPlaneRaw(self, line):
        """Get an array of (bands x samples) the given line"""
        # Note: transpose doesn't seem to automatically generate a copy, so
        # we're safe with this transpose
        s = self.raw[line, :, :].T
        return s

    def getFocalPlaneDepthRaw(self, sample, band):
        """Get an array of values at constant line, the given sample and band"""
        s = self.raw[:, sample, band]
        return s

    def getLineOfSpectraCopy(self, line):
        """Get the spectra along the given line"""
        s = self.raw[line, :, :].copy()
        return s

    def getBandBoundary(self):
        return 1

    def flatToLocation(self,pos):
        line=pos/(self.bands*self.samples)
        temp=pos%(self.bands*self.samples)
        sample=temp/self.bands
        band=temp%self.bands
        return (line,sample,band)

    def locationToFlat(self,line,sample,band):
        pos=line*self.bands*self.samples + sample*self.bands + band
        return pos


class MMapBILCubeReader(MMapCubeReader):
    def shape(self, cube):
        self.raw = numpy.reshape(self.raw, (cube.lines, cube.bands, cube.samples))

    def getPixel(self, line, sample, band):
        return self.raw[line][band][sample]

    def getBandRaw(self, band):
        """Get an array of (lines x samples) at the specified band"""
        s = self.raw[:, band, :]
        return s

    def getSpectraRaw(self, line, sample):
        """Get the spectra at the given pixel"""
        s = self.raw[line, :, sample]
        return s
    
    def getFocalPlaneRaw(self, line):
        """Get an array of (bands x samples) the given line"""
        s = self.raw[line, :, :]
        return s

    def getFocalPlaneDepthRaw(self, sample, band):
        """Get an array of values at constant line, the given sample and band"""
        s = self.raw[:, band, sample]
        return s

    def getLineOfSpectraCopy(self, line):
        """Get the spectra along the given line"""
        # FIXME: transpose doesn't automatically generate a copy in the latest
        # numpy?
        s = numpy.transpose(self.raw[line, :, :].copy())
        return s

    def getBandBoundary(self):
        return self.samples

    def flatToLocation(self,pos):
        line=pos/(self.bands*self.samples)
        temp=pos%(self.bands*self.samples)
        band=temp/self.samples
        sample=temp%self.samples
        return (line,sample,band)

    def locationToFlat(self,line,sample,band):
        pos=line*self.bands*self.samples + band*self.samples + sample
        return pos


class MMapBSQCubeReader(MMapCubeReader):
    def shape(self, cube):
        self.raw = numpy.reshape(self.raw, (cube.bands, cube.lines, cube.samples))

    def getPixel(self, line, sample, band):
        return self.raw[band][line][sample]

    def getBandRaw(self, band):
        """Get an array of (lines x samples) at the specified band"""
        s = self.raw[band, :, :]
        return s

    def getSpectraRaw(self, line, sample):
        """Get the spectra at the given pixel"""
        s = self.raw[:, line, sample]
        return s

    def getFocalPlaneRaw(self, line):
        """Get an array of (bands x samples) the given line"""
        s = self.raw[:, line, :]
        return s

    def getFocalPlaneDepthRaw(self, sample, band):
        """Get an array of values at constant line, the given sample and band"""
        s = self.raw[band, :, sample]
        return s

    def getLineOfSpectraCopy(self, line):
        """Get the spectra along the given line"""
        # FIXME: transpose doesn't automatically generate a copy in the latest
        # numpy?
        s = numpy.transpose(self.raw[:, line, :].copy())
        return s

    def getBandBoundary(self):
        return self.samples*self.lines

    def flatToLocation(self,pos):
        band=pos/(self.lines*self.samples)
        temp=pos%(self.lines*self.samples)
        line=temp/self.samples
        sample=temp%self.samples
        return (line,sample,band)

    def locationToFlat(self,line,sample,band):
        pos=band*self.lines*self.samples + line*self.samples + sample
        return pos

def getMMapCubeReader(interleave):
    i = interleave.lower()
    if i == 'bip':
        return MMapBIPCubeReader
    elif i == 'bil':
        return MMapBILCubeReader
    elif i == 'bsq':
        return MMapBSQCubeReader
    else:
        raise TypeError("Unknown interleave %s" % interleave)


class Cube(debugmixin):
    """Generic representation of an HSI datacube.  Specific subclasses
    L{BILCube}, L{BIPCube}, and L{BSQCube} exist to fill in the
    concrete implementations of the common formats of HSI data.
    """

    def __init__(self, filename=None, interleave='unknown'):
        self.url = None
        self.setURL(filename)
        
        self.samples=-1
        self.lines=-1
        self.bands=-1
        self.interleave = interleave.lower()
        self.sensor_type='unknown'

        # date/time metadata
        self.imaging_date = 0
        self.file_date = datetime.now()

        # absolute pointer to data within the file
        self.file_offset=0
        # number of header bytes to skip when reading the raw data
        # file (relative to file_offset)
        self.header_offset=0
        # data_offset = cube_offset + header_offset.  This is an
        # absolute pointer to the raw data within the file
        self.data_offset=0
        self.data_bytes=0 # number of bytes in the data part of the file

        # Data type is a numarray data type, one of: [None,Int8,Int16,Int32,Float32,Float64,Complex32,Complex64,None,None,UInt16,UInt32,Int64,UInt64]
        self.data_type=None

        self.byte_order=nativeByteOrder
        self.swap=False

        # per band information, should be lists of dimension self.bands
        self.wavelengths=[]
        self.bbl=[]
        self.fwhm=[]
        self.band_names=[]

        # wavelength units: 'nm' for nanometers, 'um' for micrometers,
        # None for unknown
        self.wavelength_units=None

        # scale_factor is the value by which the samples in the cube
        # have already been multiplied.  To get values in the range of
        # 0.0 - 1.0, you must B{divide} by this value.
        self.scale_factor=None
        
        # UTM Georeferencing information
        self.utm_zone = -1
        self.utm_origin = (0, 0)
        self.utm_pixel_size = (0, 0)
        self.utm_easting = 0
        self.utm_northing = 0

        # Lat/Long Georeferencing information
        self.georef_system = None
        self.georef_origin = (0, 0) # reference pixel location
        self.georef_pixel_size = (0, 0) # in degrees
        self.georef_lat = 0 # of upper left corner of pixel
        self.georef_long = 0 # of upper left corner of pixel

        self.description=''

        # data reader
        self.cube_io = None
        self.itemsize=0

        # calculated quantities
        self.spectraextrema=[None,None] # min and max over whole cube
        
        # progress bar indicator
        self.progress = None


    def __str__(self):
        s=StringIO()
        s.write("""Cube: filename=%s
        description=%s
        data_offset=%d header_offset=%d file_offset=%d data_type=%s
        samples=%d lines=%d bands=%d data_bytes=%d
        interleave=%s byte_order=%d (native byte order=%d)\n""" % (self.url,self.description,self.data_offset,self.header_offset,self.file_offset,str(self.data_type),self.samples,self.lines,self.bands,self.data_bytes,self.interleave,self.byte_order,nativeByteOrder))
        if self.utm_zone >= 0:
            s.write("        utm: zone=%s easting=%f northing=%f\n" % (self.utm_zone, self.utm_easting, self.utm_northing))
        if self.scale_factor: s.write("        scale_factor=%f\n" % self.scale_factor)
        s.write("        wavelength units: %s\n" % self.wavelength_units)
        # s.write("        wavelengths: %s\n" % self.wavelengths)
        s.write("        bbl: %s\n" % self.bbl)
        # s.write("        fwhm: %s\n" % self.fwhm)
        # s.write("        band_names: %s\n" % self.band_names)
        s.write("        cube_io=%s\n" % str(self.cube_io))
        return s.getvalue()

    def fileExists(self):
        return vfs.exists(self.url)
                
    def isDataLoaded(self):
        return self.cube_io is not None

    def setURL(self, url=None):
        #dprint("setting url to %s" % url)
        if url:
            self.url = vfs.normalize(url)
        else:
            self.url=None
    
    @classmethod
    def getCubeReader(cls, interleave):
        i = interleave.lower()
        try:
            cls = getMMapCubeReader(interleave)
        except TypeError:
            # Interleave not recognized; in the future will try different cube
            # readers
            raise
        return cls

    def open(self,url=None):
        if url:
            self.setURL(url)
            self.cube_io = None

        if self.url:
            if self.cube_io is None: # don't try to reopen if already open
                self.initialize()
                
                cube_io_cls = self.getCubeReader(self.interleave)
                self.cube_io = cube_io_cls(self, self.url)
                
                self.verifyAttributes()
        else:
            raise IOError("No url specified.")
    
    def save(self,url=None):
        if url:
            self.setURL(url)

        if self.url:
            self.cube_io.save(self.url)

    def initialize(self,datatype=None,byteorder=None):
        self.initializeSizes(datatype,byteorder)
        self.initializeOffset()

    def initializeOffset(self):
        if self.header_offset>0 or self.file_offset>0:
            if self.data_offset==0:
                # if it's not already set, set it
                self.data_offset=self.file_offset+self.header_offset

    def initializeSizes(self,datatype=None,byteorder=None):
        if datatype:
            self.data_type=datatype
        if byteorder:
            self.byte_order=byteorder
        
        # find out how many bytes per element in this datatype
        if self.data_type:
            self.itemsize=numpy.empty([1],dtype=self.data_type).itemsize

        # calculate the size of the raw data only if it isn't already known
        if self.data_bytes==0:
            self.data_bytes=self.itemsize*self.samples*self.lines*self.bands

    def verifyAttributes(self):
        """Clean up after loading a cube to make sure some values are
        populated and that everything that should have defaults does."""

        # supply reasonable scale factor
        if self.scale_factor == None:
            self.guessScaleFactor()

        # supply bad band list
        if not self.bbl:
            self.bbl=[1]*self.bands
        # dprint("verifyAttributes: bands=%d bbl=%s" % (self.bands,self.bbl))

        # guess wavelength units if not supplied
        if len(self.wavelengths)>0 and not self.wavelength_units:
            self.guessWavelengthUnits()

        if self.byte_order != nativeByteOrder:
            #dprint("byteswapped data!")
            #self.swap=True

            # with numarray's byteorder parameter, we don't have to
            # actually perform any swapping by hand.
            pass

        if self.url is not None:
            self.file_date = vfs.get_mtime(self.url)

    

    def guessScaleFactor(self):
        """Try to supply a good guess as to the scale factor of the
        samples based on the type of the data"""
        if self.data_type in [numpy.int8,numpy.int16,numpy.int32,numpy.uint16,numpy.uint32,numpy.int64,numpy.uint64]:
            self.scale_factor=10000.0
        elif self.data_type in [numpy.float32, numpy.float64]:
            self.scale_factor=1.0
        else:
            self.scale_factor=1.0

    def guessDisplayBands(self):
        """Guess the best bands to display a false-color RGB image
        using the wavelength info from the cube's metadata."""
        if self.bands>=3 and len(self.wavelengths)>0:
            # bands=[random.randint(0,self.bands-1) for i in range(3)]
            bands=[self.getBandListByWavelength(wl)[0] for wl in (660,550,440)]

            # If all the bands are the same, then visible light isn't
            # within the wavelength region
            if bands[0]==bands[1] and bands[1]==bands[2]:
                bands=[bands[0]]
        else:
            bands=[0]
        return bands
        
    def guessWavelengthUnits(self):
        """Try to guess the wavelength units if the wavelength list is
        supplied but the units aren't."""
        if self.wavelengths[-1]<100.0:
            self.wavelength_units='um'
        else:
            self.wavelength_units='nm'
    
    def getWavelengthStr(self, band):
        if self.wavelengths and band >=0 and band < len(self.wavelengths):
            text = "%.2f %s" % (self.wavelengths[band], self.wavelength_units)
            return text
        return "no value"

    def getDescriptiveBandName(self, band):
        """Get a text string that describes the band.
        
        Use the wavelength array and the array of band names to create a text
        string that describes the band.
        """
        text = []
        if self.wavelengths and band >=0 and band < len(self.wavelengths):
            text.append(u"\u03bb=%.2f %s" % (self.wavelengths[band], self.wavelength_units))
        if self.band_names and band >=0 and band < len(self.band_names):
            text.append(unicode(self.band_names[band]))
        return u" ".join(text)

    def updateExtrema(self, spectra):
        mn=spectra.min()
        if self.spectraextrema[0]==None or mn<self.spectraextrema[0]:
            self.spectraextrema[0]=mn
        mx=spectra.max()
        if self.spectraextrema[1]==None or  mx>self.spectraextrema[1]:
            self.spectraextrema[1]=mx

    def getUpdatedExtrema(self):
        return self.spectraextrema

    def getPixel(self,line,sample,band):
        """Get an individual pixel at the specified line, sample, & band"""
        return self.cube_io.getPixel(line, sample, band)

    def getBand(self,band):
        """Get a copy of the array of (lines x samples) at the
        specified band.  You are not working on the original data."""
        s=self.getBandInPlace(band).copy()
        if self.swap:
            s.byteswap(True)
        return s

    def getBandInPlace(self,band):
        """Get the slice of the data array (lines x samples) at the
        specified band.  This points to the actual in-memory array."""
        s=self.getBandRaw(band)
        self.updateExtrema(s)
        return s

    def getBandRaw(self,band):
        return self.cube_io.getBandRaw(band)

    def getFocalPlaneInPlace(self, line):
        """Get the slice of the data array (bands x samples) at the specified
        line, which corresponds to a view of the data as the focal plane would
        see it.  This points to the actual in-memory array.
        """
        s=self.getFocalPlaneRaw(line)
        self.updateExtrema(s)
        return s

    def getFocalPlaneRaw(self, line):
        return self.cube_io.getFocalPlaneRaw(line)

    def getFocalPlaneDepthInPlace(self, sample, band):
        """Get the slice of the data array through the cube at the specified
        sample and band.  This points to the actual in-memory array.
        """
        s=self.getFocalPlaneDepthRaw(sample, band)
        return s

    def getFocalPlaneDepthRaw(self, sample, band):
        return self.cube_io.getFocalPlaneDepthRaw(sample, band)

    def getSpectra(self,line,sample):
        """Get the spectra at the given pixel.  Calculate the extrema
        as we go along."""
        spectra=self.getSpectraInPlace(line,sample).copy()
        if self.swap:
            spectra.byteswap()
        spectra*=self.bbl
        self.updateExtrema(spectra)
        return spectra
        
    def getSpectraInPlace(self,line,sample):
        """Get the spectra at the given pixel.  Calculate the extrema
        as we go along."""
        spectra=self.getSpectraRaw(line,sample)
        return spectra

    def getSpectraRaw(self,line,sample):
        """Get the spectra at the given pixel"""
        return self.cube_io.getSpectraRaw(line, sample)

    def getLineOfSpectra(self,line):
        """Get the all the spectra along the given line.  Calculate
        the extrema as we go along."""
        spectra=self.getLineOfSpectraCopy(line)
        if self.swap:
            spectra.byteswap()
        spectra*=self.bbl
        self.updateExtrema(spectra)
        return spectra
        
    def getLineOfSpectraCopy(self,line):
        """Get the spectra along the given line.  Subclasses override
        this."""
        return self.cube_io.getLineOfSpectraCopy(line)

    def normalizeUnits(self,val,units):
        """Normalize a value in the specified units to the cube's
        default wavelength unit."""
        if not self.wavelength_units:
            return val
        cubeunits=utils.units_scale[self.wavelength_units]
        theseunits=utils.units_scale[units]
##        converted=val*cubeunits/theseunits
        converted=val*theseunits/cubeunits
        #dprint("val=%s converted=%s cubeunits=%s theseunits=%s" % (str(val),str(converted),str(cubeunits),str(theseunits)))
        return converted

    def normalizeUnitsTo(self,val,units):
        """Normalize a value given in the cube's default wavelength
        unit to the specified unit.
        """
        if not self.wavelength_units:
            return val
        cubeunits=utils.units_scale[self.wavelength_units]
        theseunits=utils.units_scale[units]
        converted=val*cubeunits/theseunits
        #dprint("val=%s converted=%s cubeunits=%s theseunits=%s" % (str(val),str(converted),str(cubeunits),str(theseunits)))
        return converted

    def getBandListByWavelength(self,wavelen_min,wavelen_max=-1,units='nm'):
        """Get list of bands between the specified wavelength, or if
        the wavelength range is too small, get the nearest band."""
        bandlist=[]
        if wavelen_max<0:
            wavelen_max=wavelen_min
        wavelen_min=self.normalizeUnits(wavelen_min,units)
        wavelen_max=self.normalizeUnits(wavelen_max,units)
        if len(self.wavelengths)==0:
            return bandlist
        
        for channel in range(self.bands):
            # dprint("wavelen[%d]=%f" % (channel,self.wavelengths[channel]))
            if (self.bbl[channel]==1 and
                  self.wavelengths[channel]>=wavelen_min and
                  self.wavelengths[channel]<=wavelen_max):
                bandlist.append(channel)
        if not bandlist:
            center=(wavelen_max+wavelen_min)/2.0
            if center<self.wavelengths[0]:
                for channel in range(self.bands):
                    if self.bbl[channel]==1:
                        bandlist.append(channel)
                        break
            elif center>self.wavelengths[self.bands-1]:
                for channel in range(self.bands-1,-1,-1):
                    if self.bbl[channel]==1:
                        bandlist.append(channel)
                        break
            else:
                for channel in range(self.bands-1):
                    if (self.bbl[channel]==1 and
                           self.wavelengths[channel]<center and
                           self.wavelengths[channel+1]>center):
                        if (center-self.wavelengths[channel] <
                               self.wavelengths[channel+1]-center):
                            bandlist.append(channel)
                            break
                        else:
                            bandlist.append(channel+1)
                            break
        return bandlist

    def getFlatView(self):
        """Get a flat, one-dimensional view of the data"""
        #self.flat=self.raw.view()
        #self.flat.setshape((self.raw.size()))
        #return self.raw.flat
        raise NotImplementedError

    def getBandBoundary(self):
        """return the number of items you have to add to a flat
        version of the data until you reach the next band in the data"""
        raise NotImplementedError

    def flatToLocation(self,pos):
        """Convert the flat index to a tuple of line,sample,band"""
        raise NotImplementedError

    def locationToFlat(self,line,sample,band):
        """Convert location (line,sample,band) to flat index"""
        return self.cube_io.locationToFlat(line, sample, band)
    
    def getBadBandList(self,other=None):
        if other:
            bbl2=[0]*self.bands
            for i in range(self.bands):
                if self.bbl[i] and other.bbl[i]:
                    bbl2[i]=1
            return bbl2
        else:
            return self.bbl
    
    def iterRawBIP(self):
        # bands vary fastest, then samples, then lines
        for i in range(self.lines):
            band = self.getFocalPlaneRaw(i).transpose()
            yield band.tostring()
    
    def iterRawBIL(self):
        # samples vary fastest, then bands, then lines
        for i in range(self.lines):
            band = self.getFocalPlaneRaw(i)
            yield band.tostring()
    
    def iterRawBSQ(self):
        # samples vary fastest, then lines, then bands 
        for i in range(self.bands):
            band = self.getBandRaw(i)
            yield band.tostring()
    
    def iterRaw(self, size, interleaveiter):
        """Iterator used to return the raw data of the cube in manageable chunks.
        
        Uses one of L{iterRawBIP}, L{iterRawBIL}, or L{iterRawBSQ} to grab the
        next chunk of data.  Once there are enough bytes to fill the requested
        size, the bytes are yielded to the calling function.  This loop
        continues until all the data has been returned to the caller.
        
        @param size: length of buffer to return at each iteration (note the
        final iteration may be shorter)
        
        @param iterleaveiter: an interleave functor taking no arguments and
        yielding chunks of data at each iteration
        """
        fh = StringIO()
        i = 0
        for bytes in interleaveiter():
            count = len(bytes)
            if (i + count) < size:
                fh.write(bytes)
                i += len(bytes)
            else:
                bi = 0
                while bi < count:
                    remaining_bytes = count - bi
                    unfilled = size - i
                    if remaining_bytes < unfilled:
                        fh.write(bytes[bi:])
                        i += remaining_bytes
                        break
                    fh.write(bytes[bi:bi + unfilled])
                    yield fh.getvalue()
                    bi += unfilled
                    fh = StringIO()
                    i = 0
        leftover = fh.getvalue()
        if len(leftover) > 0:
            yield leftover
    
    def getRawIterator(self, block_size, interleave=None):
        """Get an iterator to return the raw data of the cube in manageable
        chunks.
        
        The blocks of data returned by this iterator are in the interleave
        order supplied.  If no interleave is supplied, the current interleave
        is used.
        
        @param block_size: size of data chunks to be returned
        @param interleave: string, one of 'bip', 'bil', or 'bsq'
        @return: iterator used to loop over blocks of data, or None if unknown
        interleave
        """
        if interleave is None:
            interleave = self.interleave
        iter = {'bip': self.iterRawBIP,
                'bil': self.iterRawBIL,
                'bsq': self.iterRawBSQ,
                }.get(interleave.lower(), None)
        if iter:
            return self.iterRaw(block_size, iter)
        return None
    
    def writeRawData(self, fh, options=None, progress=None, block_size=100000):
        if options is None:
            options = dict()
        interleave = options.get('interleave', self.interleave)
        num_blocks = (self.data_bytes / block_size) + 1
        iterator = self.getRawIterator(block_size, interleave)
        if iterator:
            count = 0
            for block in iterator:
                fh.write(block)
                if progress:
                    progress((count * 100) / num_blocks)
                count += 1
        else:
            raise ValueError("Unknown interleave %s" % interleave)

    def registerProgress(self, progress):
        """Register the progress bar that cube functions may use when needed.
        
        The progress bar should conform to the L{ModularStatusBarInfo} progress
        bar methods.
        """
        self.progress = progress

    def getProgressBar(self):
        return self.progress


def newCube(interleave,url=None):
    cube = Cube(url, interleave)
    return cube

def createCube(interleave,lines,samples,bands,datatype=None, byteorder=nativeByteOrder, scalefactor=10000.0, data=None, dummy=False):
    if datatype == None:
        datatype = numpy.int16
    cube=newCube(interleave,None)
    cube.interleave=interleave
    cube.samples=samples
    cube.lines=lines
    cube.bands=bands
    cube.data_type=datatype
    cube.byte_order=byteorder
    cube.scale_factor=scalefactor
    cube.initialize(datatype,byteorder)
    
    cube_io_cls = getMMapCubeReader(interleave)
    if not dummy:
        if data:
            raw = numpy.frombuffer(data, datatype)
        else:
            raw = numpy.zeros((samples*lines*bands), dtype=datatype)
    else:
        raw = None
    cube.cube_io = cube_io_cls(cube, array=raw)
    cube.verifyAttributes()
    return cube


if __name__ == "__main__":
    c=BIPCube()
    c.samples=5
    c.lines=4
    c.bands=3
    c.raw=array(arange(c.samples*c.lines*c.bands))
    c.shape()
    print c.raw
    print c.getPixel(0,0,0)
    print c.getPixel(0,0,1)
    print c.getPixel(0,0,2)
