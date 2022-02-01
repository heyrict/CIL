# -*- coding: utf-8 -*-
#   This work is part of the Core Imaging Library (CIL) developed by CCPi 
#   (Collaborative Computational Project in Tomographic Imaging), with 
#   substantial contributions by UKRI-STFC and University of Manchester.

#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

#   Authored by:    Jakob S. Jørgensen (DTU)
#                   Andrew
#                   Edoardo Pasca (UKRI-STFC)
#                   Gemma Fardell (UKRI-STFC)


from cil.framework import AcquisitionData, AcquisitionGeometry, ImageData, ImageGeometry, DataOrder
import numpy as np
import os
import olefile
import logging
import dxchange
import warnings

logger = logging.getLogger(__name__)

class ZEISSDataReader(object):
    
    def __init__(self, file_name=None, roi=None):
        '''
        Constructor
        
        :param file_name: file name to read
        :type file_name: os.path or string
        :param roi: dictionary with roi to load for each axis.
                {'axis_labels_1': (start, end, step), 
                 'axis_labels_2': (start, end, step)}
                axis_labels are definied by ImageGeometry and AcquisitionGeometry dimension labels.
                e.g. for ImageData to skip files or to change number of files to load, 
                adjust 'vertical'. For instance, 'vertical': (100, 300)
                will skip first 100 files and will load 200 files.
                'axis_label': -1 is a shortcut to load all elements along axis.
                Start and end can be specified as None which is equivalent 
                to start = 0 and end = load everything to the end, respectively.
                Start and end also can be negative using numpy indexing.
        :type roi: dictionary, default None

        '''
        # Set logging level for dxchange reader.py
        logger_dxchange = logging.getLogger(name='dxchange.reader')
        if logger_dxchange is not None:
            logger_dxchange.setLevel(logging.ERROR)

        if file_name is not None:
            self.set_up(file_name = file_name, roi = roi)

    @property
    def file_name(self):
        return self._file_name

    def set_file_name(self, file_name):
        # check if file exists
        file_name = os.path.abspath(file_name)
        if not(os.path.isfile(file_name)):
            raise FileNotFoundError('{}'.format(file_name))
        
        file_type = os.path.basename(file_name).split('.')[-1].lower()
        if file_type not in ['txrm','txm']:
            raise TypeError('This reader can only process TXRM or TXM files. Got {}'.format(os.path.basename(self.file_name)))

        self._file_type = file_type
        self._file_name = file_name


    @property
    def full_roi(self):

        default_roi = [ [0,self._metadata_full['number_of_images'],1], 
                        [0,self._metadata_full['image_height'],1],
                        [0,self._metadata_full['image_width'],1]] 

        return default_roi


    @property
    def roi(self):
        return self._roi

    def set_roi(self, roi=None):

        if roi == None:
            self._roi = roi
        else:

            if self._file_type == 'txrm':
                allowed_labels = DataOrder.CIL_AG_LABELS
                zeis_data_order = {'angle':0, 'vertical':1, 'horizontal':2}
            else:
                allowed_labels = DataOrder.CIL_IG_LABELS
                zeis_data_order = {'vertical':0, 'horizontal_y':1, 'horizontal_x':2}

            # check roi labels and create tuple for slicing    
            roi_tmp = self.full_roi.copy()   

            for key in roi.keys():
                if key not in allowed_labels:
                    raise Exception("Wrong label. Expected dimension labels in {0}, {1}, {2}, Got {}".format(**self.full_roi.keys()), key)

                idx = zeis_data_order[key]
                if roi[key] != -1:
                    for i, x in enumerate(roi[key]):
                        if x is None:
                            continue

                        if i != 2: #start and stop
                            roi_tmp[idx][i] = x if x >= 0 else roi_tmp[idx][1] - x
                        else: #step
                            roi_tmp[idx][i] =  x if x > 0 else 1
                                
            self._roi = roi_tmp


    def set_up(self, 
               file_name,
               roi = None):
        '''Set up the reader
        
        :param file_name: file name to read
        :type file_name: os.path or string, default None
        :param roi: dictionary with roi to load for each axis.
                {'axis_labels_1': (start, end, step), 
                 'axis_labels_2': (start, end, step)}
                axis_labels are definied by ImageGeometry and AcquisitionGeometry dimension labels.
                e.g. for ImageData to skip files or to change number of files to load, 
                adjust 'vertical'. For instance, 'vertical': (100, 300)
                will skip first 100 files and will load 200 files.
                'axis_label': -1 is a shortcut to load all elements along axis.
                Start and end can be specified as None which is equivalent 
                to start = 0 and end = load everything to the end, respectively.
                Start and end also can be negative using numpy indexing.
        :type roi: dictionary, default None
        '''

        self.set_file_name(file_name)

        self._metadata_full = self.read_metadata()
    
        self.set_roi(roi)

        if self.roi:       
            self._metadata = self.slice_metadata(self._metadata_full)
        else:
            self._metadata = self._metadata_full
        
        #setup geometry using metadata
        if self._metadata_full['data geometry'] == 'acquisition':
            self._setup_acq_geometry()
        else:
            self._setup_image_geometry()

    def read_metadata(self):
        # Read one image to get the metadata
        _,metadata = dxchange.read_txrm(self.file_name,((0,1),(None),(None)))

        # Read extra metadata
        with olefile.OleFileIO(self.file_name) as ole:
            # Read source to center and detector to center distances
            StoRADistance = dxchange.reader._read_ole_arr(ole, \
                    'ImageInfo/StoRADistance', "<{0}f".format(metadata['number_of_images']))
            DtoRADistance = dxchange.reader._read_ole_arr(ole, \
                    'ImageInfo/DtoRADistance', "<{0}f".format(metadata['number_of_images']))
            
            dist_source_center = np.abs(StoRADistance[0])
            dist_center_detector = np.abs(DtoRADistance[0])

            # Read xray geometry (cone or parallel beam) and file type (TXRM or TXM)
            xray_geometry = dxchange.reader._read_ole_value(ole, 'ImageInfo/XrayGeometry', '<i')
            file_type = dxchange.reader._read_ole_value(ole, 'ImageInfo/AcquisitionMode', '<i')

            # Pixelsize loaded in metadata is really the voxel size in um.
            # We can compute the effective detector pixel size as the geometric
            # magnification times the voxel size.
            metadata['dist_source_center'] = dist_source_center
            metadata['dist_center_detector'] = dist_center_detector
            metadata['detector_pixel_size'] = ((dist_source_center+dist_center_detector)/dist_source_center)*metadata['pixel_size']

            #Configure beam and data geometries
            if xray_geometry == 1:
                logger.info('setting up cone beam geometry')
                metadata['beam geometry'] ='cone'
            else:
                logger.info('setting up parallel beam geometry')
                metadata['beam geometry'] = 'parallel'
            if file_type == 0:
                metadata['data geometry'] = 'acquisition'
            else:
                metadata['data geometry'] = 'image'
        return metadata
    
    def slice_metadata(self,metadata):
        '''
        Slices metadata to configure geometry before reading data
        '''
        image_slc = range(*self._roi[0])
        height_slc = range(*self._roi[1])
        width_slc = range(*self._roi[2])
        #These values are 0 or do not exist in TXM files and can be skipped
        if metadata['data geometry'] == 'acquisition':
            metadata['thetas'] = metadata['thetas'][image_slc]
            metadata['x_positions'] = metadata['x_positions'][image_slc]
            metadata['y_positions'] = metadata['y_positions'][image_slc]
            metadata['z_positions'] = metadata['z_positions'][image_slc]
            metadata['x-shifts'] = metadata['x-shifts'][image_slc]
            metadata['y-shifts'] = metadata['y-shifts'][image_slc]
            metadata['reference'] = metadata['reference'][height_slc.start:height_slc.stop:height_slc.step,
                                                          width_slc.start:width_slc.stop:width_slc.step]
        metadata['number_of_images'] = len(image_slc)
        metadata['image_width'] = len(width_slc)
        metadata['image_height'] = len(height_slc)
        return metadata
        
    def _setup_acq_geometry(self):
        '''
        Setup AcquisitionData container
        '''
        if self._metadata['beam geometry'] == 'cone':
            self._geometry = AcquisitionGeometry.create_Cone3D(
                [0,-self._metadata['dist_source_center'],0],[0,self._metadata['dist_center_detector'],0] \
                ) \
                    .set_panel([self._metadata['image_width'], self._metadata['image_height']],\
                        pixel_size=[self._metadata['detector_pixel_size']/1000,self._metadata['detector_pixel_size']/1000])\
                    .set_angles(self._metadata['thetas'],angle_unit=AcquisitionGeometry.RADIAN)
        else:
            self._geometry = AcquisitionGeometry.create_Parallel3D()\
                    .set_panel([self._metadata['image_width'], self._metadata['image_height']])\
                    .set_angles(self._metadata['thetas'],angle_unit=AcquisitionGeometry.RADIAN)
        self._geometry.dimension_labels =  ['angle', 'vertical', 'horizontal']

    def _setup_image_geometry(self):
        '''
        Setup ImageData container
        '''
        slices = self._metadata['number_of_images']
        width = self._metadata['image_width']
        height = self._metadata['image_height']
        voxel_size = self._metadata['pixel_size']
        self._geometry = ImageGeometry(voxel_num_x=width,
                                    voxel_size_x=voxel_size,
                                    voxel_num_y=height,
                                    voxel_size_y=voxel_size,
                                    voxel_num_z=slices,
                                    voxel_size_z=voxel_size)

    def read(self):
        '''
        Reads projections and return Acquisition (TXRM) or Image (TXM) Data container
        '''
        # Load projections or slices from file
        slice_range = None
        if self.roi:
            slice_range = tuple(self._roi)
        data, _ = dxchange.read_txrm(self.file_name,slice_range)
        
        if isinstance(self._geometry,AcquisitionGeometry):
            # Normalise data by flatfield
            data = data / self._metadata['reference']

            for num in range(self._metadata['number_of_images']):
                data[num,:,:] = np.roll(data[num,:,:], \
                    (int(self._metadata['x-shifts'][num]),int(self._metadata['y-shifts'][num])), \
                    axis=(1,0))
                
            acq_data = AcquisitionData(array=data, deep_copy=False, geometry=self._geometry.copy(),suppress_warning=True)
            return acq_data
        else:
            ig_data = ImageData(array=data, deep_copy=False, geometry=self._geometry.copy())
            return ig_data


    def get_geometry(self):
        '''
        Return Acquisition (TXRM) or Image (TXM) Geometry object
        '''
        return self._geometry

    def get_metadata(self):
        '''return the metadata of the file'''
        return self._metadata


class TXRMDataReader(ZEISSDataReader):
    def __init__(self, 
                 **kwargs):
        warnings.warn('TXRMDataReader has been deprecated and will be removed in following version. Use ZEISSDataReader instead',
              DeprecationWarning)
        logger.warning('TXRMDataReader has been deprecated and will be removed in following version. Use ZEISSDataReader instead')
        super().__init__(**kwargs)