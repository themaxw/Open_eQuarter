# -*- coding: utf-8 -*-
"""
/***************************************************************************
 OpenEQuarterMain
                                 A QGIS plugin
 The plugin automates the setup for investigating an area.
                              -------------------
        begin                : 2014-10-07
        copyright            : (C) 2014 by Kim Gülle / UdK-Berlin
        email                : kimonline@posteo.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# Import the PyQt and QGIS libraries
from socket import gaierror
import sys
import httplib
import unittest
import time
import os

from PyQt4.QtGui import *
from PyQt4.QtCore import SIGNAL, Qt, QSettings, QVariant
from qgis.gui import QgsMapToolEmitPoint
from qgis.core import *
from qgis.utils import iface

from model.progress_model import ProgressItemsModel
from view.oeq_dialogs import (
    Modular_dialog, ProjectSettings_form, ProjectDoesNotExist_dialog,
    ColorPicker_dialog, MainProcess_dock, RequestWmsUrl_dialog,
    EstimatedEnergyDemand_dialog)
from qgisinteraction import plugin_interaction
from qgisinteraction import layer_interaction
from qgisinteraction import raster_layer_interaction
from qgisinteraction import project_interaction
from qgisinteraction import wms_utils
from tests import layer_interaction_test
from mole.project import config
from mole.stat_util.building_evaluation import evaluate_building

def isnull(value):
    return type(value) is type(NULL)

class OpenEQuarterMain:

    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface

        ### Monitor the users progress
        self.progress_items_model = ProgressItemsModel()

        ### UI specific settings
        # Create the dialogues (after translation) and keep references
        self.oeq_project_settings_form = ProjectSettings_form()
        self.color_picker_dlg = ColorPicker_dialog()
        self.project_does_not_exist_dlg = ProjectDoesNotExist_dialog()
        self.request_wms_url_dlg = RequestWmsUrl_dialog()
        self.coordinate_tracker = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.wms_url = 'crs=EPSG:3068&dpiMode=7&format=image/png&layers=0&styles=&url=http://fbinter.stadt-berlin.de/fb/wms/senstadt/k5'
        self.confirm_selection_of_investigation_area_dlg = Modular_dialog()
        self.main_process_dock = None

        ### Project specific settings
        # the project path equals './' as long as the project has not been saved
        self.project_path = os.path.normpath(QgsProject.instance().readPath(''))
        self.oeq_project = ''

        # OpenStreetMap-plugin-layer
        self.open_layer = None

        ### Default values
        # name of the shapefile which will be created to define the investigation area
        self.investigation_shape_layer_style = os.path.join(config.plugin_dir, 'project', 'oeq_ia_style.qml')

    def initGui(self):
        plugin_icon = QIcon(os.path.join(':/Plugin/icons/OeQ_plugin_icon.png'))
        self.main_action = QAction(plugin_icon, u"OpenEQuarter-Process", self.iface.mainWindow())
        self.main_action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.main_action)
        self.iface.addPluginToMenu(u"&OpenEQuarter", self.main_action)

        clipping_icon = QIcon(os.path.join(':','Plugin', 'icons', 'scissor.png'))
        self.clipping_action = QAction(clipping_icon, u"Extract extent from active WMS", self.iface.mainWindow())
        self.clipping_action.triggered.connect(lambda: self.clip_from_raster(self.iface.activeLayer()))
        self.iface.addToolBarIcon(self.clipping_action)
        self.iface.addPluginToMenu(u"&OpenEQuarter", self.clipping_action)

        testing_icon = QIcon(os.path.join(':','Plugin', 'icons', 'lightbulb.png'))
        self.testing_action = QAction(testing_icon, u"Run all unit-tests", self.iface.mainWindow())
        self.testing_action.triggered.connect(lambda: self.run_tests())
        self.iface.addToolBarIcon(self.testing_action)
        self.iface.addPluginToMenu(u"&OpenEQuarter", self.testing_action)

        self.iface.connect(QgsMapLayerRegistry.instance(), SIGNAL('legendLayersAdded(QList< QgsMapLayer * >)'), self.reorder_layers)
        self.iface.connect(QgsProject.instance(), SIGNAL('readProject(const QDomDocument &)'), self.open_progress)
        self.iface.connect(QgsProject.instance(), SIGNAL('projectSaved()'), self.save_progress)

        self.initGui_process_dock()

    def initGui_process_dock(self):
        self.main_process_dock = MainProcess_dock(self.progress_items_model)

        self.main_process_dock.process_button_next.clicked.connect(self.continue_process)
        self.main_process_dock.process_button_auto.clicked.connect(self.auto_run)

        sections = self.progress_items_model.section_views
        for list_view in sections:
            list_view.clicked.connect(self.process_button_clicked)

        settings_dropdown_menu = QMenu()
        config_icon = QIcon(os.path.join(':', 'Controls', 'icons', 'config.png'))
        open_icon = QIcon(os.path.join(':', 'Controls', 'icons', 'open.png'))
        save_icon = QIcon(os.path.join(':', 'Controls', 'icons', 'save_active.png'))
        settings_dropdown_menu.addAction(config_icon, 'Project configuration..', self.open_settings)
        settings_dropdown_menu.addAction(save_icon, 'Save current progress', self.save_progress)
        settings_dropdown_menu.addAction(open_icon, 'Open OeQ-Project..', self.open_progress)

        tools_dropdown_menu = QMenu()
        tools_dropdown_menu.addAction('Color Picker', self.handle_legend_created)
        tools_dropdown_menu.addAction('Load layer from WMS', self.load_wms)
        tools_dropdown_menu.addAction('Save extent as image', lambda: wms_utils.save_wms_extent_as_image(self.iface.activeLayer().name()))
        tools_dropdown_menu.addAction('Calculate Energy Demand', self.handle_estimated_energy_demand)

        self.main_process_dock.tools_dropdown_btn.setMenu(tools_dropdown_menu)
        self.main_process_dock.settings_dropdown_btn.setMenu(settings_dropdown_menu)

    def reorder_layers(self):
        """
        Reorder the layers so that they are ordered (from top to bottom) as follows:
            1. investigation_area
            2. housing_coordinate_layer
            3. housing_layer
        :return:
        :rtype:
        """
        position = -1
        if layer_interaction.find_layer_by_name(config.investigation_shape_layer_name):
            position += 1
            layer_interaction.move_layer_to_position(self.iface, config.investigation_shape_layer_name, position)

        if layer_interaction.find_layer_by_name(config.housing_coordinate_layer_name):
            position += 1
            layer_interaction.move_layer_to_position(self.iface, config.housing_coordinate_layer_name, position)

        if layer_interaction.find_layer_by_name(config.housing_layer_name):
            position += 1
            layer_interaction.move_layer_to_position(self.iface, config.housing_layer_name, position)

    def open_settings(self):
        self.oeq_project_settings_form.show()

    def open_progress(self, doc):
        self.project_path = os.path.normpath(QgsProject.instance().readPath(''))
        progress = os.path.join(self.project_path, 'oeq_progress.oeq')
        if os.path.isfile(progress):
            self.progress_items_model.load_section_models(progress)
            if self.main_process_dock.isVisible():
                self.main_process_dock.setVisible(False)
                self.initGui_process_dock()
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.main_process_dock)

        else:
            self.progress_items_model.load_section_models(config.progress_model)
            if self.main_process_dock.isVisible():
                self.main_process_dock.setVisible(False)
                self.initGui_process_dock()
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.main_process_dock)
            else:
                self.initGui_process_dock()

    def save_progress(self):
        self.project_path = os.path.normpath(QgsProject.instance().readPath(''))

        while self.project_path == './':
            self.project_path = os.path.normpath(QgsProject.instance().readPath(''))
            iface.actionSaveProject().trigger()

        self.progress_items_model.save_section_models(self.project_path)

    def load_wms(self):
        print('Load wms')

    # ToDo Check if this has to be put in a separate method
    def refresh_layer_list(self):
        """
        Update the color-pickers layer-dropdown with a list of the currently visible .tif-files
        :return:
        :rtype:
        """
        dropdown = self.color_picker_dlg.layers_dropdown
        dropdown.clear()
        wms_list = layer_interaction.get_wms_layer_list(self.iface, visibility='visible')

        layer = None
        for layer in wms_list:
            source = layer.publicSource()
            if os.path.basename(source).endswith('.tif'):
                dropdown.addItem(layer.name())
                self.color_picker_dlg.color_entry_manager.add_layer(layer.name())

        layer_interaction.move_layer_to_position(self.iface, layer, 0)

    def handle_canvas_click(self, point, button):
        """
        Handle a user's click on the map-canvas.
        :param point: Coordinates of the point which was clicked
        :type point: QgsPoint
        :param button: The (mouse-)button which triggered the signal
        :type button: Qt::MouseButton
        :return:
        :rtype:
        """
        canvas = self.iface.mapCanvas()
        crs = canvas.mapRenderer().destinationCrs()
        raster = self.iface.activeLayer()

        if raster is not None:
            color = raster_layer_interaction.extract_color_at_point(raster, point, crs)

            if isinstance(color, QColor):
                self.color_picker_dlg.add_color(color)

    def unload(self):
        """
        Called, when the plugin is uninstalled to remove the plugin menu item and icons
        :return:
        :rtype:
        """
        self.iface.removePluginMenu(u"&OpenEQuarter", self.main_action)
        self.iface.removePluginMenu(u"&OpenEQuarter", self.clipping_action)
        self.iface.removePluginMenu(u"&OpenEQuarter", self.testing_action)
        self.iface.removeToolBarIcon(self.main_action)
        self.iface.removeToolBarIcon(self.clipping_action)
        self.iface.removeToolBarIcon(self.testing_action)
        self.main_process_dock.disconnect(QgsMapLayerRegistry.instance(), SIGNAL('legendLayersAdded(QList< QgsMapLayer * >)'), self.reorder_layers)
        self.main_process_dock.disconnect(QgsProject.instance(), SIGNAL('readProject(const QDomDocument &)'), self.open_progress)

    def create_project_ifNotExists(self):
        """
        If the current workspace has not been saved as a project, prompt the user to "Save As..." project
        :return:
        :rtype:
        """
        if not project_interaction.project_exists():
            # prompt the user to save the project
            self.project_does_not_exist_dlg.show()
            yes_to_save = self.project_does_not_exist_dlg.exec_()

            if yes_to_save:
                iface.actionSaveProjectAs().trigger()
                self.project_path = QgsProject.instance().readPath('./')

    def osm_layer_is_loaded(self):
        """
        Iterate over all layers and check if an osm plugin-layer exists.
        :return True if the layer is available:
        :rtype bool:
        """
        for layer in QgsMapLayerRegistry.instance().mapLayers():
            if 'OpenLayers_plugin_layer' in layer:
                return True

        return False

    def zoom_to_default_extent(self):
        """
        Set the extent of the open layer to the default extent and scale specified as in config.default_extent and self.default_scale
        :return:
        :rtype:
        """
        try:
            canvas = self.iface.mapCanvas()
            map_crs = canvas.mapSettings().destinationCrs()
            source_crs = QgsCoordinateReferenceSystem(config.default_extent_crs)
            transformer = QgsCoordinateTransform(source_crs, map_crs)
            extent = transformer.transform(config.default_extent)

            self.open_layer.setExtent(extent)
            self.iface.setActiveLayer(self.open_layer)
            self.iface.actionZoomToLayer().trigger()

        except None, Error:
            print(self.__module__, 'Could not zoom to default extent: {}'.format(Error))

    def confirm_selection_of_investigation_area(self, layer_name):
        """
        Select the layer named 'layer_name' from layers list and trigger the ToggleEditing button
        :param layer_name: Name of the layer whose editing mode shall be triggered
        :type layer_name: str
        :return:
        :rtype:
        """
        if layer_name and not layer_name.isspace():

            edit_layer = layer_interaction.find_layer_by_name(layer_name)

            # if the layer was found, prompt the user to confirm the adding-feature-process was finished
            if edit_layer:

                self.confirm_selection_of_investigation_area_dlg.show()
                is_confirmed = self.confirm_selection_of_investigation_area_dlg.exec_()
                return is_confirmed

    # method currently not in use
    def request_wms_layer_url(self):
        """
        Open a dialog and request an url to a wms-server. Check if the given url is valid, by trying to connect to the server.
        :return:
        :rtype:
        """
        self.request_wms_url_dlg.show()
        url_confirmed = self.request_wms_url_dlg.exec_()

        # if 'ok' was hit, get the url
        if url_confirmed:
            wms_url = self.request_wms_url_dlg.wms_url.text()

            try:
                if wms_url.startswith("http"):
                    socket = httplib.HTTPConnection(wms_url[7:])
                    socket.connect()
                else:
                    socket = httplib.HTTPConnection(wms_url)
                    socket.connect()

            except (httplib.HTTPException, gaierror) as InetException:
                print(self.__module__, 'Exception {} occured. URL seems to be invalid!'.format(InetException))
                return

            self.wms_url = wms_url

    def set_project_crs(self, crs):
        """
        Set the project crs to the given crs and do a re-projection to keep the currently viewed extent focused
        :param crs: The new crs to set the project to
        :type crs: str
        :return:
        :rtype:
        """
        # if the given crs is valid
        if not crs.isspace() and QgsCoordinateReferenceSystem(crs):

            canvas = self.iface.mapCanvas()

            extent = canvas.extent()  # save formerly viewed extent
            current_crs = self.get_project_crs()  # get project-crs
            current_scale = canvas.scale()

            renderer = canvas.mapRenderer()
            new_crs = QgsCoordinateReferenceSystem(crs)
            renderer.setDestinationCrs(new_crs)

            canvas.zoomScale(current_scale)

            if not current_crs == new_crs:
                # set extent, by transforming the formerly saved extent to new Projection
                coord_transformer = QgsCoordinateTransform(current_crs, new_crs)
                extent = coord_transformer.transform(extent)

            canvas.setExtent(extent)
            canvas.refresh()

    def get_project_crs(self):
        """
        Return the project crs
        :return: The project crs
        :rtype: QgsCoordinateReferenceSystem
        """

        canvas = iface.mapCanvas()
        crs = canvas.mapSettings().destinationCrs()

        return crs

    def clip_from_raster(self, raster_layer):
        """
        Clip the current extent from the given raster-layer
        :param raster_layer: The raster-layer which will be clipped
        :type raster_layer: QgsRasterLayer
        :return:
        :rtype:
        """
        try:
            # set the rasterlayer as active, since only the active layer will be clipped and start the export
            self.iface.setActiveLayer(raster_layer)
            geo_export_path = wms_utils.save_wms_extent_as_image(raster_layer.name())
            pyramids_built = raster_layer_interaction.gdal_addo_layerfile(geo_export_path, 'gauss', 6)
            if pyramids_built != 0:
                print 'Error number {} occured, while building pyramids.'.format(pyramids_built)
        except AttributeError as NoneException:
            print(self.__module__, NoneException)
            return None

        filename = geo_export_path.split(os.path.sep)[-1]
        filename = os.path.splitext(filename)[0]
        no_timeout = 50
        while not os.path.exists(geo_export_path) and no_timeout:
            time.sleep(0.1)
            no_timeout -= 1

        raster_layer = QgsRasterLayer(geo_export_path, filename)

        # if the crs is invalid, prompt the user to define an CRS
        if not raster_layer.crs().authid():
            old_validation = str(QSettings().value('/Projections/defaultBehaviour', 'prompt'))
            QSettings().setValue('/Projections/defaultBehaviour', 'prompt')
            layer_interaction.add_layer_to_registry(raster_layer)
            QSettings().setValue('/Projections/defaultBehaviour', old_validation)
        else:
            old_validation = str(QSettings().value('/Projections/defaultBehaviour', 'useProject'))
            QSettings().setValue('/Projections/defaultBehaviour', 'useProject')
            layer_interaction.add_layer_to_registry(raster_layer)
            QSettings().setValue('/Projections/defaultBehaviour', old_validation)

        return raster_layer.name()

    # step 0.0
    def handle_ol_plugin_installed(self):
        return plugin_interaction.get_plugin_ifexists(config.ol_plugin_name) is not None

    # step 0.1
    def handle_pst_plugin_installed(self):
        return plugin_interaction.get_plugin_ifexists(config.pst_plugin_name) is not None

    # step 0.2
    def handle_real_centroid_plugin_installed(self):
        return plugin_interaction.get_plugin_ifexists(config.real_centroid_plugin_name) is not None

    # step 0.3
    def handle_project_created(self):
        # if no project exists, create one first
        self.create_project_ifNotExists()
        self.project_path = os.path.normpath(QgsProject.instance().readPath('./'))

        # if project was created stop execution
        if self.project_path != './':
            return True
        else:
            return False

    # step 0.4
    def handle_osm_layer_loaded(self):
        if self.osm_layer_is_loaded():
            return True

        else:
            ol_plugin = plugin_interaction.OlInteraction(config.ol_plugin_name)

            if ol_plugin.open_osm_layer(config.open_layer_type_id):
                layer_dict = QgsMapLayerRegistry.instance().mapLayers()
                for layer_name, layer in layer_dict.iteritems():
                    if 'OpenLayers_plugin_layer' in layer_name:
                        self.open_layer = layer
                        break

                self.zoom_to_default_extent()
                return True

            else:
                return False

    # step 1.0
    def handle_temp_shapefile_created(self):
        investigation_area = layer_interaction.create_temporary_layer(config.investigation_shape_layer_name, 'Polygon',
                                                                     config.project_crs)

        if investigation_area is not None:
            layer_interaction.add_style_to_layer(self.investigation_shape_layer_style, investigation_area)
            layer_interaction.add_layer_to_registry(investigation_area)
            return True
        else:
            return False

    # step 1.1
    def handle_editing_temp_shapefile_started(self):
        layer_interaction.trigger_edit_mode(self.iface, config.investigation_shape_layer_name)
        return True

    # step 1.2
    def handle_investigation_area_selected(self):
        self.confirm_selection_of_investigation_area_dlg.set_dialog_text(
            "Click 'OK' once the investigatoion area is selected.", "Define investigaion area")
        ia_covered = self.confirm_selection_of_investigation_area(config.investigation_shape_layer_name)
        return ia_covered

    # step 1.3
    def handle_editing_temp_shapefile_stopped(self):
        layer_interaction.trigger_edit_mode(self.iface, config.investigation_shape_layer_name, 'off')
        try:
            investigation_area = layer_interaction.find_layer_by_name(config.investigation_shape_layer_name)
            disk_layer = layer_interaction.write_vector_layer_to_disk(investigation_area, os.path.join(self.project_path, investigation_area.name()))
        except IOError, Error:
            print(self.__module__, 'The "Investigation Area"-layer could not be saved to disk: ', Error)
        try:
            if disk_layer.isValid():
                layer_interaction.hide_or_remove_layer(config.investigation_shape_layer_name, 'remove')
                layer_interaction.add_layer_to_registry(disk_layer)
                layer_interaction.add_style_to_layer(self.investigation_shape_layer_style, disk_layer)
                # trigger the edit-mode, to have the style displayed.
                layer_interaction.trigger_edit_mode(self.iface, disk_layer.name())
                layer_interaction.trigger_edit_mode(self.iface, disk_layer.name(), 'off')
                disk_layer.setLayerName(config.investigation_shape_layer_name)
                self.iface.setActiveLayer(disk_layer)
                self.iface.actionZoomToLayer().trigger()
        except AttributeError, NoneTypeError:
            print(self.__module__, 'The "Investigation Area"-layer could not be saved to disk: ', NoneTypeError)

        return True

    # step 2.0
    def handle_housing_layer_loaded(self):
        user_dir = os.path.expanduser('~')
        housing_layer = os.path.join(user_dir, 'Hausumringe EPSG3857', 'Hausumringe EPSG3857.shp')
        if os.path.exists(housing_layer):
            housing_layer = layer_interaction.load_layer_from_disk(housing_layer, config.housing_layer_name)
            investigation_area = layer_interaction.find_layer_by_name(config.investigation_shape_layer_name)
            out_layer = os.path.join(self.project_path, config.housing_layer_name + '.shp')

            intersection_done = layer_interaction.intersect_shapefiles(housing_layer, investigation_area, out_layer)
            if intersection_done:
                out_layer = layer_interaction.load_layer_from_disk(out_layer, config.housing_layer_name)
                layer_interaction.add_layer_to_registry(out_layer)
                layer_interaction.edit_housing_layer_attributes(out_layer)
            return intersection_done

    # step 2.1
    def handle_building_coordinates_loaded(self):
        # ToDo
        return True

    # step 3.0
    def handle_raster_loaded(self):
        # self.request_wms_layer_url()
        raster_layers = []
        raster_layers.append(layer_interaction.open_wms_as_raster(self.iface, 'crs=EPSG:3068&dpiMode=7&format=image/png&layers=2&styles=&url=http://fbinter.stadt-berlin.de/fb/wms/senstadt/alk_gebaeude', 'Floors'))
        raster_layers.append(layer_interaction.open_wms_as_raster(self.iface, 'crs=EPSG:3068&dpiMode=7&format=image/png&layers=0&styles=&url=http://fbinter.stadt-berlin.de/fb/wms/senstadt/gebaeudealter', 'YOC'))

        raster_loaded = False
        for raster in raster_layers:
            try:
                if raster.isValid():
                    layer_interaction.add_layer_to_registry(raster)
                    self.iface.setActiveLayer(raster)
                    raster_loaded = True
            except AttributeError as NoneTypeError:
                print(self.__module__, NoneTypeError)

        if not raster_loaded:
            self.iface.actionAddWmsLayer().trigger()

        # returns True, since either the clipped raster was loaded or the add-raster-menu was opened
        return True

    # step 3.1
    def handle_extent_clipped(self):
        try:
            investigation_shape = layer_interaction.find_layer_by_name(config.investigation_shape_layer_name)
            # an investigation shape is needed, to trigger the zoom to layer function
            if investigation_shape is not None and investigation_shape.featureCount() > 0:
                # zoom
                self.iface.setActiveLayer(investigation_shape)
                self.iface.actionZoomToLayer().trigger()

                # clip extent from visible raster layers
                # save visible layers and set them invisible afterwards, to prevent further from the wms-server
                raster_layers = layer_interaction.get_wms_layer_list(self.iface, 'visible')
                for layer in raster_layers:
                    self.iface.legendInterface().setLayerVisible(layer, False)

                extracted_layers = []
                for clipping_raster in raster_layers:
                    extracted_layers.append(self.clip_from_raster(clipping_raster))

        except AttributeError as NoneException:
            print(self.__module__, NoneException)
            return False

        try:
            layer_interaction.hide_or_remove_layer(self.open_layer.name(), 'hide', self.iface)
        except AttributeError, NoneTypeError:
            print(self.__module__, NoneTypeError)

        for layer_name in extracted_layers:
            try:
                layer = layer_interaction.find_layer_by_name(layer_name)
                raster_layer_interaction.gdal_warp_layer(layer, config.project_crs)
                path_geo = layer.publicSource()
                path_transformed = path_geo.replace('_geo.tif', '_transformed.tif')

                no_timeout = 50
                while not os.path.exists(path_transformed) and no_timeout:
                    time.sleep(0.1)
                    no_timeout -= 1

                if os.path.exists(path_transformed):
                    # change validation to surpress missing-crs prompt
                    old_validation = str(QSettings().value('/Projections/defaultBehaviour', 'useProject'))
                    QSettings().setValue('/Projections/defaultBehaviour', 'useProject')

                    layer_interaction.hide_or_remove_layer(layer_name, 'remove', self.iface)
                    rlayer = QgsRasterLayer(path_transformed, layer_name)
                    rlayer.setCrs(QgsCoordinateReferenceSystem(config.project_crs))
                    QgsMapLayerRegistry.instance().addMapLayer(rlayer)
                    os.remove(path_geo)
                    self.iface.mapCanvas().refresh()
                    # restore former settings
                    QSettings().setValue('/Projections/defaultBehaviour', old_validation)
            except (OSError, AttributeError) as Clipping_Error:
                print(self.__module__, Clipping_Error)
                pass

        time.sleep(1.0)
        return True

    # step 3.2
    def handle_legend_created(self):
        self.coordinate_tracker.canvasClicked.connect(self.handle_canvas_click)
        self.iface.mapCanvas().setMapTool(self.coordinate_tracker)
        self.color_picker_dlg.refresh_layers_dropdown.clicked.connect(self.refresh_layer_list)
        self.refresh_layer_list()

        dropdown = self.color_picker_dlg.layers_dropdown
        dropdown.currentIndexChanged.connect(self.color_picker_dlg.update_color_values)
        dropdown.currentIndexChanged.connect(lambda: layer_interaction.move_layer_to_position(self.iface, dropdown.currentText(), 0))
        layer_interaction.move_layer_to_position(self.iface, dropdown.currentText(), 0)
        self.color_picker_dlg.show()
        save_or_abort = self.color_picker_dlg.exec_()

        if save_or_abort:
            layer = self.iface.activeLayer()
            out_path = os.path.dirname(layer.publicSource())
            out_path = os.path.join(out_path, layer.name() + '.txt')
            self.color_picker_dlg.update_color_values()
            self.iface.actionPan().trigger()
            entry_written = self.color_picker_dlg.color_entry_manager.write_map_to_disk(layer.name(), out_path)
            if entry_written:
                QMessageBox.information(self.iface.mainWindow(), 'Success', 'Legend was successfully written to "{}".'.format(out_path))
                self.reorder_layers()
                return True
        else:
            self.iface.actionPan().trigger()
            self.reorder_layers()

    # step 4.0
    def handle_generate_real_centroids(self):
        rci = plugin_interaction.RealCentroidInteraction(config.real_centroid_plugin_name)
        polygon = config.housing_layer_name
        output = os.path.join(self.project_path, config.pst_input_layer_name + '.shp')
        centroid_layer = rci.create_centroids(polygon, output)

        if centroid_layer.isValid():
            layer_interaction.add_layer_to_registry(centroid_layer)
            polygon = layer_interaction.find_layer_by_name(polygon)
            rci.calculate_accuracy(polygon, centroid_layer)
            layer_interaction.add_style_to_layer(config.valid_centroids_style, centroid_layer)
            self.reorder_layers()
            return True
        else:
            return False

    # step 4.1
    def handle_information_sampled(self):
        psti = plugin_interaction.PstInteraction(iface, config.pst_plugin_name)
        psti.set_input_layer(config.pst_input_layer_name)
        abbreviations = psti.select_and_rename_files_for_sampling()
        pst_output_layer = psti.start_sampling(self.project_path, config.pst_output_layer_name)
        vlayer = QgsVectorLayer(pst_output_layer, layer_interaction.biuniquify_layer_name('pst_out'), "ogr")

        # in case the plugin was re-started, reload the color-entries
        for layer_name, abbreviation in abbreviations.iteritems():
            in_path = os.path.join(self.project_path, layer_name + '.txt')
            self.color_picker_dlg.color_entry_manager.read_color_map_from_disk(in_path)
            layer_color_map = self.color_picker_dlg.color_entry_manager.layer_values_map
            color_dict = layer_color_map[layer_name]
            layer_interaction.add_parameter_info_to_layer(color_dict, abbreviation, vlayer)

        layer_interaction.add_layer_to_registry(vlayer)
        return True

    #step 4.2
    def handle_estimated_energy_demand(self):
        # ToDo Change to non default-values
        pop_dens = 3927
        area = NULL
        perimeter = NULL
        building_height = NULL
        default_yoc = 1948
        default_acc_heat_hours=72000
        
        dlg = EstimatedEnergyDemand_dialog()
        dlg.show()
        start_calc = dlg.exec_()
        if start_calc:
            # ToDo It has to be checked, if the in- and out-layer have the same amount of features
            in_layer = layer_interaction.find_layer_by_name(dlg.input_layer.currentText())
            out_layer = layer_interaction.find_layer_by_name(dlg.output_layer.currentText())
            att_name = dlg.field_name.text()[:10]
            provider = in_layer.dataProvider()
            out_provider = out_layer.dataProvider()

            
            area_fld = dlg.area.currentText()
            peri_fld = dlg.perimeter.currentText()
            yoc_fld = dlg.yoc.currentText()
            floors_fld = dlg.floors.currentText()
            

            for feat in provider.getFeatures():
                bld_yoc=feat.attribute(yoc_fld)
                if isnull(bld_yoc): bld_yoc=default_yoc
                est_ed = evaluate_building(population_density=pop_dens,
                area=feat.attribute("AREA"),
                perimeter=feat.attribute("PERIMETER"),
                floors=feat.attribute(floors_fld),
                year_of_construction=bld_yoc,
                accumulated_heating_hours=default_acc_heat_hours)
                attributes=[QgsField(i, QVariant.Double) for i in est_ed.keys()]
                layer_interaction.add_attributes_if_not_exists(out_layer, attributes)
                name_index = [out_provider.fieldNameIndex(i) for i in est_ed.keys()]
                values =  {name_index[n]: est_ed.values()[n] for n in range(len(name_index))}
                out_provider.changeAttributeValues({feat.id() : values})
 
            return True
        else:
            return False

    def continue_process(self):
        """
        Call the appropriate handle-function, depending on the progress-step, that has to be executed next.
        :return:
        :rtype:
        """
        last_view = self.progress_items_model.section_views[-1]

        i = 0
        while last_view.model().item(i):
            i += 1

        last_step_name = last_view.model().item(i-1).accessibleText()
        first_open_item = self.progress_items_model.check_prerequisites_for(last_step_name)
        first_open_item.setCheckState(1)

        handler = 'handle_{}'.format(first_open_item.accessibleText())
        next_call = getattr(self, handler)
        is_done = next_call()

        QgsProject.instance().setDirty(True)
        # Set the items state to 2 or 0, since its state is represented by a tristate checkmark
        if is_done:
            first_open_item.setCheckState(2)
        else:
            first_open_item.setCheckState(0)

    def process_button_clicked(self, model_index):
        """
        Call the appropriate handle-function, depending on the QStandardItem which triggered the function call.
        :param model_index: The senders model_index
        :type model_index: QModelIndex
        :return:
        :rtype:
        """
        model = model_index.model()
        row = model_index.row()
        item = model.item(row)
        clicked_step = item.accessibleText()

        # for debugging uncomment the following line
        if True:
        # if self.progress_items_model.check_prerequisites_for(clicked_step):
            QgsProject.instance().setDirty(True)
            item.setCheckState(1)
            handler = 'handle_' + clicked_step
            step_call = getattr(self, handler)
            is_done = step_call()
            # Set the items state to 2 or 0, since its state is represented by a tristate checkmark
            if is_done:
                item.setCheckState(2)
            else:
                item.setCheckState(0)

    def run(self):
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.main_process_dock)

        if self.oeq_project == '':
            self.oeq_project_settings_form.show()
            save_or_abort = self.oeq_project_settings_form.exec_()

        if save_or_abort:

            municipal = self.oeq_project_settings_form.municipals[0]

            if len(municipal) > 0:
                index = 0
                if isinstance(self.oeq_project_settings_form.location_city, QComboBox):
                    index = self.oeq_project_settings_form.location_city.currentIndex()
                try:
                    municipal = self.oeq_project_settings_form.municipals[index]
                    x = municipal['GEO_L']
                    y = municipal['GEO_W']
                    scale = 0.05
                    extent = QgsRectangle(x - scale, y - scale, x + scale, y + scale)
                    config.default_extent = extent
                    config.default_extent_crs = 'EPSG:4326'
                except (IndexError, KeyError), Error:
                    print(self.__module__, Error)

            self.check_status()
            self.auto_run()

    def run_tests(self):
        test_class = layer_interaction_test.LayerInteraction_test
        test_loader = unittest.TestLoader()
        test_names = test_loader.getTestCaseNames(test_class)

        print(test_names)
        suite = unittest.TestSuite()
        for test_method in test_names:
            suite.addTest(test_class(test_method))

        unittest.TextTestRunner(sys.stdout).run(suite)

    def check_status(self):
        """
        Check the user's current progress and where the process should be continued.
        :return:
        :rtype:
        """
        self.continue_process() #OL-Plugin
        self.continue_process() #PST-Plugin
        self.continue_process() #Proje. saved

        investigation_layer = layer_interaction.find_layer_by_name(config.investigation_shape_layer_name)

        if self.osm_layer_is_loaded() or investigation_layer:
            self.set_next_step_done(True) # open OL-map

            if investigation_layer:
                self.set_next_step_done(True) # create shapefile

                if investigation_layer.featureCount() > 0:
                    self.set_next_step_done(True) # activate edit mode
                    self.set_next_step_done(True) # confirm selection
                    self.set_next_step_done(True) # deactivate edit mode

    def set_next_step_done(self, is_done):
        """
        Find the next step in the progress model and change its status to is_done
        :param is_done: The status of the next step
        :type is_done: bool
        :return:
        :rtype:
        """
        last_view = self.progress_items_model.section_views[-1]

        i = 0
        while last_view.model().item(i):
            i += 1

        last_step_name = last_view.model().item(i-1).accessibleText()
        next_open_item = self.progress_items_model.check_prerequisites_for(last_step_name)

        next_open_item.setCheckState(is_done)

    def auto_run(self):
        """
        Iterate through the progress step by step and successively auto-initiate each step,
        once its prerequisites are given.
        :return:
        :rtype:
        """
        for view in self.progress_items_model.section_views:
            model = view.model()
            no_timeout = 20
            i = 0
            while model.item(i) and no_timeout:
                if model.item(i).checkState() != 2:
                    self.continue_process()

                i += 1
                no_timeout -= 1

        # execute continue process to make sure all steps were executed
        self.continue_process()