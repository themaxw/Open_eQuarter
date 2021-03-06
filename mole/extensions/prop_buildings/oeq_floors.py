# -*- coding: utf-8 -*-

import os,math
from qgis.core import NULL
from mole import oeq_global
from mole.project import config
from mole.extensions import OeQExtension
from mole.stat_corr import rb_contemporary_base_uvalue_by_building_age_lookup

def calculation(self=None, parameters={},feature = None):
    return {}


extension = OeQExtension(
    extension_id=__name__,
    category='Evaluation',
    subcategory='General',
    extension_name='Number of Floors',
    layer_name= 'Number of Floors',
    extension_filepath=os.path.join(__file__),
    colortable = os.path.join(os.path.splitext(__file__)[0] + '.qml'),
    field_id='FLOORS',
    source_type='none',
    par_in=['FLOORS'],
    sourcelayer_name=config.data_layer_name,
    targetlayer_name=config.data_layer_name,
    active=True,
    show_results=['FLOORS'],
    description=u"Number of Floors",
    evaluation_method=calculation)

extension.registerExtension(default=True)
