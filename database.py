import io
import os.path
import sqlite3

import numpy as np
import pandas as pd


###############################################################################
# Teach the database engine how to record numpy arrays.
###############################################################################

def adapt_array(arr):
    '''Take a numpy array and return an sqlite record.'''
    assert arr.shape == (4,5), 'Data matrix should have 4 rows and 5 cols.'
    out = io.BytesIO()
    np.save(out, arr)
    out.seek(0)
    return sqlite3.Binary(out.read())

def convert_array(text):
    '''Take an sqlite record and return a numpy array.'''
    out = io.BytesIO(text)
    out.seek(0)
    return np.load(out)

sqlite3.register_adapter(np.ndarray, adapt_array)
sqlite3.register_converter("REACTOR_ARRAY", convert_array)


###############################################################################
# Open the database file. If such file does not exists, create a new database.
###############################################################################

new_db = not os.path.isfile('reactor_database.sqlite')
db = sqlite3.connect('reactor_database.sqlite', detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
db.row_factory = sqlite3.Row
if new_db:
    db.executescript('''

    -- Species that the reactor knows how to work with.
    CREATE TABLE species (
        name TEXT PRIMARY KEY NOT NULL,
        description TEXT,
        light_ratio_to_od_formula TEXT NOT NULL, -- not properly type checked whether it is actual python math expression
        od_to_biomass_formula TEXT NOT NULL,
        od_to_cell_count_formula TEXT NOT NULL
   );

    -- The table of experiments ran and running on the reactor.
    CREATE TABLE experiments (
        name TEXT PRIMARY KEY NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        description TEXT,
        species_name TEXT NOT NULL REFERENCES species(name) ON DELETE CASCADE,
        row1 TEXT,
        row2 TEXT,
        row3 TEXT,
        row4 TEXT,
        col1 TEXT,
        col2 TEXT,
        col3 TEXT,
        col4 TEXT,
        col5 TEXT
    );

    -- All notes attached to experiments while they are being executed.
    CREATE TABLE notes (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        note TEXT
    );

    -- The following tables all contain measurements.
    -- The table names are of the form quantity__unit (with a double
    -- underscore).

    -- Light intensity sent to each well (above water measurement)
    CREATE TABLE light_in__uEm2s (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );

    -- Light intensity captured above each well
    CREATE TABLE light_out__uEm2s (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );

    -- Temperature
    CREATE TABLE temperature__C (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );

    -- Added water
    CREATE TABLE water__ml (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );

    -- Added media
    CREATE TABLE media__ml (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );

    -- Drained volume
    CREATE TABLE drained__ml (
        timestamp TIMESTAMP PRIMARY KEY DEFAULT CURRENT_TIMESTAMP NOT NULL,
        experiment_name TEXT NOT NULL REFERENCES experiments(name) ON DELETE CASCADE,
        data REACTOR_ARRAY
    );
    ''')


###############################################################################
# Helper functions.
###############################################################################

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
                           params=(experiment,))
    return df

def parse_formula(experiment, formula):
    with db:
        query = db.execute('''SELECT species_name FROM experiments
                              WHERE experiment=?''',
                           (experiment,))
        species = next(query)[0]
        query = db.execute('''SELECT ''')



###############################################################################
# Add or remove mock data to the database.
###############################################################################

def add_mock_data():
    '''Generate a mock species and experiments and add data points to each.'''
    import datetime
    import numpy as np
    now = datetime.datetime.now()
    hour = datetime.timedelta(0,3600)
    day  = datetime.timedelta(1)
    ones = np.ones((4,5))
    rand = lambda : np.random.random((4,5))*2-1
    with db:
        db.execute('''INSERT INTO species (name, light_ratio_to_od_formula,
                                           od_to_biomass_formula, od_to_cell_count_formula)
                      VALUES ('mock_species', '-log(x)', 'x', 'x')''')
        for m in range(5):
            db.execute('''INSERT INTO experiments (name, description, species_name, timestamp)
                          VALUES (?, ?, 'mock_species', ?)''',
                          ('mock%d'%m, lorem_ipsum if m==3 else None, now+m*day))
            for i in range(20):
                db.execute('''INSERT INTO light_in__uEm2s  (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones))
                db.execute('''INSERT INTO light_out__uEm2s (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones*0.95**i+rand()*0.05))
                db.execute('''INSERT INTO temperature__C   (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones*34+rand()*0.5))
                db.execute('''INSERT INTO water__ml        (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones+rand()*0.1))
                db.execute('''INSERT INTO media__ml        (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones*0))
                db.execute('''INSERT INTO drained__ml      (experiment_name, timestamp, data)
                              VALUES (?, ?, ?)''',
                           ('mock%d'%m, now+i*hour+m*day, ones*0))
        db.executemany('''INSERT INTO notes (experiment_name, note, timestamp) VALUES ('mock0', ?, ?)''',
                       [(s, now+i*hour*3) for i,s in enumerate(
                           ['Hello, this is a note!',
                            'Well, are you not the most beautiful bacteria!',
                            'They told me I will get famous in grad school!',
                            'You, little bacteria, are my only true friend!',
                            'Yay, happy hour!',
                            'Buffalo'+' buffalo'*200+'.'])])

def del_mock_data():
    '''Delete the mock data (relies on automatic CASCADEing).'''
    with db:
        db.execute('''DELETE FROM species WHERE name='mock_species' ''')

lorem_ipsum = '''
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut placerat tristique
libero, ac porta nisl. Nulla rhoncus justo metus, finibus ullamcorper erat
posuere a. Nulla fermentum venenatis felis id scelerisque. Vivamus vitae justo
quis massa placerat laoreet. Vivamus vehicula felis sit amet ultricies semper.
In tempus turpis ipsum, vel consectetur urna ornare non. Vivamus et condimentum
metus, vel interdum nibh. Praesent lacinia lacinia ante ut placerat. Vivamus ac
lorem fringilla, varius nulla at, egestas arcu. Etiam malesuada lacus non urna
hendrerit dapibus. Duis id elementum felis.Nam iaculis fermentum fermentum.
Aliquam vulputate fermentum libero in accumsan. Cras et nibh et mauris sagittis
sodales quis vitae risus. Fusce lobortis tincidunt urna ac tincidunt. In eu
scelerisque ipsum, et fermentum mauris. In hac habitasse platea dictumst.
Vestibulum in elit metus. Quisque sit amet eleifend ante. Curabitur vehicula
sem risus, a accumsan purus mattis non. Nullam eget nisi magna. Etiam ex
tortor, venenatis a cursus vel, molestie nec velit. Nam ac augue aliquet,
accumsan urna sed, sagittis lorem. Curabitur nec finibus libero, non lobortis
libero.Praesent feugiat egestas euismod. Lorem ipsum dolor sit amet,
consectetur adipiscing elit. Quisque tempor, ante facilisis dapibus varius,
libero purus auctor nunc, ac placerat urna nibh sed nisi. Ut ante nisl,
vestibulum vel arcu ac, ultrices laoreet felis. Vivamus elementum elementum
lacinia. Suspendisse vel leo tristique, efficitur sem tempus, cursus metus.
Cras congue libero dolor, id vehicula tellus semper non. Sed vel mi est. Mauris
feugiat placerat leo accumsan scelerisque. Pellentesque eu orci tempor,
ultrices lacus quis, malesuada nulla. Quisque iaculis dictum tellus in
euismod.Sed ultricies, orci in faucibus suscipit, sapien massa rutrum leo,
pretium suscipit nulla felis sed libero. Etiam dui neque, viverra eget
convallis sit amet, vulputate eu lectus. Proin molestie pellentesque enim, eu
elementum mauris congue non. Praesent in facilisis dolor, sit amet maximus
nulla. Proin eu erat eget massa sollicitudin convallis. Aenean ut consectetur
neque, eu scelerisque purus. Nulla facilisi.Vivamus pretium sapien vitae
fringilla pharetra. Ut sed eleifend neque. Nullam convallis commodo ultrices.
Praesent eu posuere dolor. Donec ultricies, massa varius pellentesque
porttitor, neque ex facilisis lorem, ut lobortis turpis lectus quis odio.
Vestibulum elementum mauris non tempor sodales. Ut ac maximus libero, in
lobortis sem. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam
ac mauris diam. Vivamus non risus sagittis, porta est et, porta mauris. Aenean
odio massa, commodo eget fringilla eget, accumsan tempor odio. Integer egestas
iaculis ornare. Donec euismod quam et odio aliquet suscipit. Integer euismod,
lectus a facilisis egestas, nulla libero pellentesque sapien, vel pellentesque
mi tellus aliquet odio. Nunc risus quam, commodo id rhoncus vel, vulputate vel
lectus.Integer mattis consequat tincidunt. Aenean bibendum tristique enim id
lacinia. Morbi ut fringilla ante. Curabitur blandit pretium nunc non mollis.
Pellentesque et tempor augue. Aliquam porta convallis velit, non congue elit
porta vel. Nunc accumsan nisl eu congue varius.Curabitur ut tincidunt urna, vel
congue sapien. Duis nisl lorem, dapibus sed bibendum sit amet, ullamcorper sed
libero. Etiam efficitur dictum mauris, vitae maximus nisi scelerisque nec.
Vivamus maximus.
'''

if new_db:
    add_mock_data()
