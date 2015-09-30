# -*- coding: utf-8 -*-

import os,math
from qgis.core import NULL
from mole import oeq_global
from mole.project import config
from mole.extensions import OeQExtension
from mole.stat_corr import contemporary_base_uvalue_by_building_age_lookup

def calculation(self=None, parameters={}):
    from scipy.constants import golden
    from math import floor, ceil
    from PyQt4.QtCore import QVariant
    # factor for golden rule
    dataset = {'HLAP': NULL}
    dataset.update(parameters)
    living_area = float(dataset['AREA']) * float(dataset['FLOORS'])*0.8
    qtp_total = float(dataset['BS_QTP'])
    qtp_total = qtp_total + float(dataset['RF_QTP'])
    qtp_total = qtp_total + float(dataset['WL_QTP'])
    qtp_total = qtp_total + float(dataset['WN_QTP'])*1.2
    dataset['HLAP']=qtp_total/living_area
    result = {}
    for i in dataset.keys():
        result.update({i: {'type': QVariant.Double,
                           'value': dataset[i]}})
    return result


extension = OeQExtension(
    extension_id=__name__,

    category='Evaluation',
    subcategory='Building',
    extension_name='Building Quality (QT per Livig Area, Present)',
    layer_name= 'QT Building per Livig Area Present',
    extension_filepath=os.path.join(__file__),
    colortable = os.path.join(__file__[:-3] + '.qml'),
    field_id='HLAP',
    source_type='none',
    par_in=['AREA','FLOORS','BS_QTP','RF_QTP','WL_QTP','WN_QTP'],
    layer_in=config.data_layer_name,
    layer_out=config.data_layer_name,
    active=True,
    show_results=['HLAP'],
    description=u"Calculate the present Transmission Heat Loss per Living Area",
    evaluation_method=calculation)

extension.registerExtension(default=True)
