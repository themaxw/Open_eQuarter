# -*- coding: utf-8 -*-

import os,math
from qgis.core import NULL
from mole import oeq_global
from mole.project import config
from mole.extensions import OeQExtension
from mole.stat_corr import rb_contemporary_base_uvalue_by_building_age_lookup

def calculation(self=None, parameters={},feature = None):
    from math import floor, ceil
    from PyQt4.QtCore import QVariant

    ahdph = NULL
    if not oeq_global.isnull([parameters['HLAPH']]):
        ahdph= float(parameters['HLAPH']) + 40.0 * 0.8
        # Air Change Heatloss for standard Rooms 40kWh/m2a nach Geiger Lüftung im Wohnungsbau
        # 20% of the Total Area are used for stairs and floors
    return {'AHDPH': {'type': QVariant.Double, 'value': ahdph}}


extension = OeQExtension(
    extension_id=__name__,

    category='Evaluation',
    subcategory='Building',
    extension_name='AHD Building per Living Area Present Heritage',
    layer_name= 'Annual Heat Demand (per Living Area, Present Heritage)',
    extension_filepath=os.path.join(__file__),
    colortable = os.path.join(os.path.splitext(__file__)[0] + '.qml'),
    field_id='AHDPH',
    source_type='none',
    par_in=['HLAPH'],
    sourcelayer_name=config.data_layer_name,
    targetlayer_name=config.data_layer_name,
    active=True,
    show_results=['AHDPH'],
    description=u"Calculate present heritage Annual Heat Demand per Living Area",
    evaluation_method=calculation)

extension.registerExtension(default=True)
