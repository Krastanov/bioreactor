import collections
import itertools

import numpy as np
import pandas as pd

from database import db


def read_experiment(experiment, table):
    '''Read one of the measurement tables or notes for a given experiment as a dataframe.'''
    with db:
        all_tables = [_[0] for _ in
                      db.execute('''SELECT name FROM sqlite_master
                                    WHERE type='table'
                                    AND name GLOB '*__*' ''')]
    assert table in all_tables+['notes'], 'No such table.'
    df = pd.read_sql_query('SELECT * FROM %s WHERE experiment_name=? ORDER BY timestamp ASC'%table,
                           db,
                           index_col='timestamp',
                           params=(experiment,))
    return df


###############################################################################
# Tools for calculating variables of interested dependent on logged variables.
###############################################################################

def parse_formula(experiment, formula):
    '''Return a python function corresponding to the given formula and experiment's strain.'''
    with db:
        query = db.execute('''SELECT strain_name FROM experiments
                              WHERE name=?''',
                           (experiment,))
        strain = query.fetchone()[0]
        query = db.execute('''SELECT %s FROM strains
                              WHERE name=?'''%formula,
                           (strain,))
        formula = query.fetchone()[0]
    formula = eval('lambda x:'+formula, np.__dict__)
    return formula

def read_OD(experiment):
    '''Prepare a dataframe of OD values.'''
    light_in  = read_experiment(experiment, 'light_in__uEm2s')
    light_out = read_experiment(experiment, 'light_out__uEm2s')
    OD = light_in.copy()
    OD['data'] = light_out['data']/light_in['data']
    formula = parse_formula(experiment, 'light_ratio_to_od_formula')
    OD['data'] = OD['data'].apply(formula)
    return OD

def read_cell_count(experiment):
    '''Prepare a dataframe of biomass values.'''
    OD = read_OD(experiment)
    formula = parse_formula(experiment, 'od_to_cell_count_formula')
    OD['data'] = OD['data'].apply(formula)
    return OD

def read_biomass(experiment):
    '''Prepare a dataframe of biomass values.'''
    OD = read_OD(experiment)
    formula = parse_formula(experiment, 'od_to_biomass_formula')
    OD['data'] = OD['data'].apply(formula)
    return OD


###############################################################################
# Tools to access all variables that migth be of interest (logged or calculated).
###############################################################################

# A convenient container for everything necessary to define a plot.
PlotType = collections.namedtuple('PlotType', ['reader', 'min', 'max'])

# Most of the database-to-dataframe functions need to read a single table,
# so we are making a function that returns such reader functions.
make_reader = lambda table: lambda experiment: read_experiment(experiment, table)

# A container of all predefined plots.
possible_plots = collections.OrderedDict([
        ('light in'      , PlotType(make_reader('light_in__uEm2s') ,  0,  3)),
        ('light out'     , PlotType(make_reader('light_out__uEm2s'),  0,  3)),
        ('temperature'   , PlotType(make_reader('temperature__C')  , 20, 40)),
        ('added water'   , PlotType(make_reader('water__ml')       ,  0,  5)),
        ('added media'   , PlotType(make_reader('media__ml')       ,  0,  5)),
        ('drained volume', PlotType(make_reader('drained__ml')     ,  0,  5)),
        ('OD'            , PlotType(read_OD                        ,  0,  3)),
        ('cell count'    , PlotType(read_cell_count                ,  0,  3)),
        ('biomass'       , PlotType(read_biomass                   ,  0,  3)),
        ])

def read_plottype(experiment, plot_type):
    '''Prepare a dataframe with all the data of interest for a given experiment and plot type.'''
    df = plot_type.reader(experiment)
    del df['experiment_name']
    df['avg'] = df['data'].apply(lambda _:_.mean())
    df['median'] = df['data'].apply(lambda _:np.median(_))
    df['min'] = df['data'].apply(lambda _:_.min())
    df['max'] = df['data'].apply(lambda _:_.max())
    for r in range(4):
        df['r%d'%(r+1)] = df['data'].apply(lambda _:_[r,:].mean())
    for c in range(5):
        df['c%d'%(c+1)] = df['data'].apply(lambda _:_[:,c].mean())
    for r,c in itertools.product(range(4),range(5)):
        df['%s%s'%(r+1,c+1)]=df['data'].apply(lambda _:_[r,c])
    del df['data']
    return df

def read_all_plottypes(experiment, interpolate=True):
    '''Like `read_plottype` but for all defined plot types. Interpolation is optional.'''
    ts = [read_plottype(experiment,v) for v in possible_plots.values()]
    df = pd.concat([_.transpose() for _ in ts], keys=possible_plots.keys()).transpose()
    df.columns.names = ['plot type', 'well']
    if interpolate:
        df.interpolate(method='time', limit_direction='both')
    return df
