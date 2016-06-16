import collections
import html
import inspect
import threading
import os.path

import cherrypy
from cherrypy._cperror import HTTPRedirect

from database import db, read_experiment
from scheduler import events


###############################################################################
# HTML Template class based on `str` that can escape HTML strings.
###############################################################################
# XXX Should have used actuall templating library.
class Template(str):
    '''HTML escape all strings in `format` except keyword arguments starting with "HTML".'''
    def format(self, *args, **kwargs):
        args = (html.escape(_) if isinstance(_, str) else _
                for _ in args)
        kwargs = {k: html.escape(_) if (isinstance(_, str) and not k.startswith('HTML')) else _
                  for k, _ in kwargs.items()}
        return super().format(*args, **kwargs)


###############################################################################
# HTML template for the common part of the UI.
###############################################################################

t_main = Template('''\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Yale Environmental Engineering Rapid Prototyping Bioreactor</title>
<link rel="stylesheet" href="/web_resources/pure.0.6.0.min.css">
<link rel="stylesheet" href="/web_resources/font-awesome.4.6.3.min.css">
<link rel="stylesheet" href="/web_resources/custom.css">
<script src="/web_resources/custom.js"></script>
<script>reloadTimeout();</script>
</head>
<body>
<div id="dark_layer" class="dark-class" style="display:none"><h1>Refreshing Page<h1></div>
<nav class="pure-menu pure-menu-horizontal">
    <a href="#" class="pure-menu-heading pure-menu-link">RPB</a>
    <ul class="pure-menu-list">
        <li class="pure-menu-item"><a href="/"        class="pure-menu-link">Status</a></li>
        <li class="pure-menu-item"><a href="/new"     class="pure-menu-link">New Experiment</a></li>
        <li class="pure-menu-item"><a href="/archive" class="pure-menu-link">Archive</a></li>
        <li class="pure-menu-item"><a href="/strains" class="pure-menu-link">Strain</a></li>
    </ul>
</nav>
<article class="pure-g">
<div class="pure-u-1">
{HTMLmain_article}
</div>
</article>
<footer>
Built with nanpy, cherrypy, sqlite, bokeh, purecss, and more by Hegarty, Krastanov, and Racharaks.
</footer>
</body>
</html>
''')


###############################################################################
# The "setup a new experiment" template.
###############################################################################

t_new = Template('''
<h1>New Experiment</h1>
<form class="pure-form pure-form-aligned" method="POST" action="/do_start_new_experiment">
    <fieldset>
        <legend>General</legend>
        <div class="pure-control-group">
            <label for="name">Experiment Name</label>
            <input id="name" name="name" type="text" placeholder="">
        </div>

        <div class="pure-control-group">
            <label for="strain">Strain</label>
            <input id="strain" name="strain" type="text" placeholder="">
        </div>

        <div class="pure-control-group">
            <label for="temp">Initial Temperature</label>
            <input id="temp" name="temp" type="text" placeholder="">
        </div>

        <div class="pure-control-group">
            <label for="light">Initial Light Levels</label>
            <input id="light" name="light" type="text" placeholder="">
        </div>

        <div class="pure-control-group">
            <label for="description">Description</label>
            <textarea id="description" name="description" placeholder=""></textarea>
        </div>
    </fieldset>

    <fieldset>
        <legend>Well Details</legend>
        <div class="pure-control-group">
            <label for="">Row Notes</label>
            <input id="row1" name="row1" class="pure-u-1-8" type="text" placeholder="row 1">
            <input id="row2" name="row2" class="pure-u-1-8" type="text" placeholder="row 2">
            <input id="row3" name="row3" class="pure-u-1-8" type="text" placeholder="row 3">
            <input id="row4" name="row4" class="pure-u-1-8" type="text" placeholder="row 4">
        </div>

        <div class="pure-control-group">
            <label for="">Column Notes</label>
            <input id="col1" name="col1" class="pure-u-1-8" type="text" placeholder="col 1">
            <input id="col2" name="col2" class="pure-u-1-8" type="text" placeholder="col 2">
            <input id="col3" name="col3" class="pure-u-1-8" type="text" placeholder="col 3">
            <input id="col4" name="col4" class="pure-u-1-8" type="text" placeholder="col 4">
            <input id="col5" name="col5" class="pure-u-1-8" type="text" placeholder="col 5">
        </div>
    </fieldset>

    <fieldset>
        <legend>Configuration</legend>
        {HTMLevents}
    </fieldset>

    <div class="pure-controls">
        <button type="submit" class="pure-button pure-button-primary">Start Experiment</button>
    </div>
</form>
''')

# Template for the configuration for a single event type.
t_new_event = Template('''
<div>
<h5>{event_name}</h5>
<p>{event_description}</p>
<div class="pure-controls">
<label><input id="{event_name}__check" name="{event_name}__check" type="checkbox"> Include this event type!</label>
</div>
{HTMLevent_arguments}
</div>
''')

# Template for an argument field (multiple arguments per event type).
t_new_event_args = Template('''
<div class="pure-control-group">
    <label for="{event_name}_{arg}">{arg}</label>
    <input id="{event_name}_{arg}" name="{event_name}_{arg}" placeholder="" type="text">
</div>
''')

def format_event_arguments(event):
    '''Given an event, return a form with all arguments for that event.'''
    arguments = list(inspect.signature(event.__init__).parameters)[1:]
    arguments_html='\n'.join([t_new_event_args.format(
                                event_name=event.__name__,
                                arg=arg)
                              for arg in arguments])
    return arguments_html

def format_new_html():
    '''Create a configuration page for the setup of a new experiment.'''
    events_html='\n'.join([t_new_event.format(
                             event_name=e.__name__,
                             event_description=e.__doc__,
                             HTMLevent_arguments=format_event_arguments(e))
                           for e in events])
    return t_main.format(HTMLmain_article=t_new.format(HTMLevents=events_html))


###############################################################################
# The archive template (list of all experiments).
###############################################################################

t_archive = Template('''
<h1>Archive</h1>
<script src="/web_resources/list.1.2.0.min.js"></script>
<div id='experiments'>
<div>
    <form class="pure-form">
    <fieldset>
    <legend>Search and sort experiments:</legend>
    <input class="list_search" placeholder="Search">
    <button type="button" class="list_sort pure-button" data-sort="list_name">     Sort by name         </button>
    <button type="button" class="button-xsmall pure-button" onClick="experimentsList.sort('list_name',     {{order:'desc'}});">invert</button>
    <button type="button" class="list_sort pure-button" data-sort="list_timestamp">Sort by starting time</button>
    <button type="button" class="button-xsmall pure-button" onClick="experimentsList.sort('list_timestamp',{{order:'desc'}});">invert</button>
    <button type="button" class="list_sort pure-button" data-sort="list_strain">  Sort by strain      </button>
    <button type="button" class="button-xsmall pure-button" onClick="experimentsList.sort('list_strain',  {{order:'desc'}});">invert</button>
    </fieldset>
    </form>
</div>
<ul class='list_list boxed-list'>
{HTMLarchive_entries}
</ul>
</div>
<script>
var options = {{
  valueNames: [ 'list_name', 'list_timestamp', 'list_strain', 'list_description', 'list_rows', 'list_cols', 'list_description', 'list_notes' ],
  listClass: 'list_list',
  searchClass: 'list_search',
  sortClass: 'list_sort'
}};

var experimentsList = new List('experiments', options);
</script>
''')

# A template for an entry in the list of experiments.
t_archive_entry = Template('''
<li class="pure-g fixed-height-block" id="experiments_{name}">
    <div class="pure-u-11-12">
        <h3 class="list_name"><a href="/experiment/{name}">{name}</a></h3>
    </div>
    <div class="pure-u-1-12">
        <button class="button-trash pure-button" onClick="deleteNearestLI(this);"><i class="fa fa-trash"></i></button>
    </div>
    <div class="pure-u-1-6">
        <dl>
        <dt>Starting time:</dt>
        <dd><time class="list_timestamp">{timestamp:%Y-%m-%d %H:%M:%S}</time></dd>
        <dt>Strain:</dt>
        <dd class="list_strain">{strain_name}</dd>
        </dl>
        <table class="pure-table">
        <thead><tr><th>R#</th><th>Notes</th></tr></thead>
        <tr><td>1</td><td>{row1}</td></tr>
        <tr><td>2</td><td>{row2}</td></tr>
        <tr><td>3</td><td>{row3}</td></tr>
        <tr><td>4</td><td>{row4}</td></tr>
        <thead><tr><th>C#</th><th>Notes</th></tr></thead>
        <tr><td>1</td><td>{col1}</td></tr>
        <tr><td>2</td><td>{col2}</td></tr>
        <tr><td>3</td><td>{col3}</td></tr>
        <tr><td>4</td><td>{col4}</td></tr>
        <tr><td>5</td><td>{col5}</td></tr>
        </table>
    </div>
    <div class="pure-u-1-3">
        <h4>Description</h4>
        <div class="list_description max-height-scroll">{description}</div>
    </div>
    <div class="pure-u-1-2">
        {HTMLnotes}
    </div>
</li>
''')

def format_archive_html():
    '''Load all experiments from the database and list them in the HTML template.'''
    with db:
        entries = '\n'.join(t_archive_entry.format(HTMLnotes=format_notes_html(r['name']),
                                                   **r)
                            for r in db.execute('''SELECT * FROM experiments
                                                   ORDER BY timestamp DESC'''))
    return t_main.format(HTMLmain_article=t_archive.format(HTMLarchive_entries=entries))


# Template for presenting a note.
t_note_main = Template('''
<h4>Notes</h4>
<div class="list_notes max-height-scroll">
<form class="pure-form" method="POST" action="/do_add_note">
    <textarea class="pure-input-1" name="note"></textarea>
    <input type="hidden" value="{experiment_name}" name="experiment_name">
    <button type="submit" class="button-xsmall pure-button pure-button-primary pure-input-1">Add Note</button>
</form>
<ul class="boxed-list">
{HTMLnotes}
</ul>
</div>
''')
t_note = Template('''
<li class="pure-g" id="notes_{timestamp}">
<div class="pure-u-4-5">
<h5><time>{timestamp:%Y-%m-%d %H:%M:%S}</time></h5>
</div>
<div class="pure-u-1-5">
<button class="button-trash pure-button" onClick="deleteNearestLI(this);"><i class="fa fa-trash"></i></button>
</div>
<div class="pure-u-1">{note}</div>
</li>
''')

def format_notes_html(experiment):
    '''Prepare a list of all notes for a given experiment.'''
    with db:
        notes = db.execute('''SELECT timestamp, note FROM notes
                              WHERE experiment_name=?
                              ORDER BY timestamp DESC''',
                           (experiment,))
    return t_note_main.format(HTMLnotes='\n'.join(t_note.format(**r) for r in notes),
                              experiment_name=experiment)


###############################################################################
# The experiment template describing a single experiment.
###############################################################################

t_experiment = Template('''
<h1><a href="/experiment/{name}">Experiment: {name}</a></h1>
<link rel="stylesheet" href="/web_resources/bokeh.0.11.1.min.css">
<div class="pure-g">
<div class="pure-u-1">
{HTMLlinks}
</div>
<div class="pure-u-3-4">
<script src="/web_resources/bokeh.0.11.1.min.js"></script>
{HTMLbokeh}
</div>
<div class="pure-u-1-4">
{HTMLnotes}
</div>
</div>
''')

# A convenient container for everything necessary to define a plot.
PlotType = collections.namedtuple('PlotType', ['reader', 'min', 'max'])

# Most of the database-to-dataframe functions need to read a single table,
# so we are making a function that returns such reader functions.
make_reader = lambda table: lambda experiment: read_experiment(experiment, table)

def read_OD(experiment):
    '''Prepare a dataframe of OD values.'''
    light_in  = read_experiment(experiment, 'light_in_uEm2s')
    light_out = read_experiment(experiment, 'light_out_uEm2s')
    OD = light_in.copy()
    OD['data'] = light_out['data']/light_in['data']


# A container of all predefined plots.
possible_plots = collections.OrderedDict([
        ('light in'      , PlotType(make_reader('light_in__uEm2s') ,  0,  3)),
        ('light out'     , PlotType(make_reader('light_out__uEm2s'),  0,  3)),
        ('temperature'   , PlotType(make_reader('temperature__C')  , 20, 40)),
        ('added water'   , PlotType(make_reader('water__ml')       ,  0,  5)),
        ('added media'   , PlotType(make_reader('media__ml')       ,  0,  5)),
        ('drained volume', PlotType(make_reader('drained__ml')     ,  0,  5)),
        ('OD'            , PlotType(make_reader('light_out__uEm2s'),  0,  3)),
        ])

def format_bokeh_plot_html(experiment, plot_type):
    '''Generate the HTML for a given experiment/plot combination.'''
    import itertools
    from bokeh.embed import components
    from bokeh.io import gridplot, vplot, hplot
    from bokeh.models import ColumnDataSource, Range1d, Rect, HoverTool
    from bokeh.plotting import figure
    plot_type = possible_plots[plot_type]

    # Prepare the data.
    df = plot_type.reader(experiment)
    for r,c in itertools.product(range(4),range(5)):
        df[str((r,c))]=df['data'].apply(lambda _:_[r,c])
    for r in range(4):
        df['r%d'%r] = df['data'].apply(lambda _:_[r,:].mean())
    for c in range(5):
        df['c%d'%c] = df['data'].apply(lambda _:_[:,c].mean())
    df['avg'] = df['data'].apply(lambda _:_.mean())
    df['min'] = df['data'].apply(lambda _:_.min())
    df['max'] = df['data'].apply(lambda _:_.max())
    ds = ColumnDataSource(df)

    # Summary plot (average over all wells).
    tools = 'pan,wheel_zoom,box_zoom,reset,resize,crosshair'
    webgl = False
    bottom = min(df['min'].min(), plot_type.min)
    top    = max(df['max'].max(), plot_type.max)
    left   = df['timestamp'].min()
    right  = df['timestamp'].max()
    range_y = Range1d(bottom, top)
    range_x = Range1d(left, right)
    p_mean = figure(width=350, height=350, x_axis_type='datetime',
		    toolbar_location=None, tools=tools,
                    x_range=range_x, y_range=range_y,
                    webgl=webgl)
    p_mean.line(source=ds, x='timestamp', y='avg', color='black', legend='avg', line_width=2)
    p_mean.line(source=ds, x='timestamp', y='max', color='red',   legend='max',  line_width=2)
    p_mean.line(source=ds, x='timestamp', y='min', color='blue',  legend='min',  line_width=2)
    p_mean.border_fill_color = "white"
    p_mean.legend.background_fill_alpha = 0.5

    # Add hover notes to the summary plot.
    notes = read_experiment(experiment, 'notes')
    notes['str_date'] = notes['timestamp'].apply(lambda _:_.strftime('%Y-%m-%d %H:%M:%S'))
    notes_ds = ColumnDataSource(notes)
    box = Rect(height=top-bottom,
               width=(df['timestamp'].max()-df['timestamp'].min()).total_seconds()*1e3/20,
               x='timestamp',
               y=(top+bottom)/2,
               fill_color='red', fill_alpha=0.2, line_color='red', line_alpha=0.6)
    box_r = p_mean.add_glyph(source_or_glyph=notes_ds, glyph=box)
    box_hover = HoverTool(renderers=[box_r], tooltips='<div style="width: 100px;"><h4>@str_date</h4><p>@note</p></div>')
    p_mean.add_tools(box_hover)

    # Grid plots (small plots, one for each well).
    plots = []
    for r in range(4):
        cols = []
        for c in range(5):
            p = figure(width=100, height=100, x_axis_type='datetime',
        	       min_border_top=2, min_border_right=2,
        	       min_border_bottom=20, min_border_left=20,
        	       toolbar_location=None,
        	       tools=tools,
        	       x_range=range_x, y_range=range_y,
                       webgl=webgl)
            p.line(source=ds, x='timestamp', y=str((r,c)))
            p.xaxis.major_label_orientation = 3.14/4
            p.xaxis.major_label_text_font_size = '0.6em'
            p.yaxis.major_label_text_font_size = '0.6em'
            cols.append(p)
        plots.append(cols)
    p_wells = gridplot(plots, toolbar_location='above')

    # Row plots (one line per row of wells).
    colors = ['#66c2a5','#fc8d62','#8da0cb','#e78ac3','#a6d854']
    p_rows = figure(width=350, height=430, x_axis_type='datetime',
		    toolbar_location=None, tools=tools,
		    x_range=range_x, y_range=range_y,
                    webgl=webgl)
    for r in range(4):
        p_rows.line(source=ds, x='timestamp', y='r%d'%r, color=colors[r], legend='row %d'%(r+1), line_width=2)
    p_rows.legend.background_fill_alpha = 0.5

    # Column plots (one line per column of wells).
    p_cols = figure(width=500, height=350, x_axis_type='datetime',
		    toolbar_location=None, tools=tools,
		    x_range=range_x, y_range=range_y,
                    webgl=webgl)
    for c in range(5):
        p_cols.line(source=ds, x='timestamp', y='c%d'%c, color=colors[c], legend='col %d'%(c+1), line_width=2)
    p_cols.legend.background_fill_alpha = 0.5

    # Final layout and html generation.
    final_plot = vplot(hplot(p_mean, p_cols), hplot(p_rows, p_wells))
    bokeh_script, bokeh_div = components(final_plot)
    return bokeh_div+'\n'+bokeh_script

def format_experiment_html(experiment, plot_type):
    '''Load all data for a given experiment, make bokeh plots, and load in the HTML template.'''
    links = ''.join('''<a class='pure-button {button_type}' href='/experiment/{experiment}/{plot_type}'>{plot_type}</a>
                    '''.format(button_type='pure-button-active' if p==plot_type else '',
                               experiment=experiment,
                               plot_type=p)
                    for p in possible_plots.keys())
    return t_main.format(HTMLmain_article=t_experiment.format(
        name=experiment,
        HTMLlinks=links,
        HTMLbokeh=format_bokeh_plot_html(experiment, plot_type),
        HTMLnotes=format_notes_html(experiment)
        ))


###############################################################################
# The current experiment status template.
###############################################################################

t_status = Template('''
<h1>Current Status</h1>
<div class="pure-g">
<div class="pure-u-1"><button class="pure-button button-error"> Stop </button></div>
<div class="pure-u-1">{experiment_name} ({strain}): {description}</div>
<div class="pure-u-3-4">plots</div>
<div class="pure-u-1-4">
    <div>upcoming events</div>
    <div>{HTMLnotes}</div>
</div>
</div>
''')

def format_status_html():
    '''Create a status page for the current experiment.'''
    from scheduler import current_experiment
    if current_experiment is None:
        return t_main.format(HTMLmain_article='<h1>No Experiments Running</h1>')
    with db:
        c = db.execute('''SELECT strain_name, description FROM experiments
                       WHERE name=?''',
                       (current_experiment,))
        strain, description = c.fetchone()
    return t_main.format(HTMLmain_article=t_status.format(experiment_name=current_experiment,
                                                          strain=strain,
                                                          description=description,
                                                          HTMLnotes=format_notes_html(current_experiment)))


###############################################################################
# The UI server implementation.
###############################################################################

class Root:
    @cherrypy.expose
    def index(self):
        return format_status_html()

    @cherrypy.expose
    def archive(self):
        return format_archive_html()

    @cherrypy.expose
    def experiment(self, name, plot_type='light out'):
        return format_experiment_html(name, plot_type)

    @cherrypy.expose
    def new(self):
        return format_new_html()

    @cherrypy.expose
    def do_delete(self, table, entry):
        '''Delete an entry from a permitted table.'''
        ids = {'experiments': 'name',
               'notes'      : 'timestamp'}
        primary_key = ids[table]
        with db:
            db.execute('''DELETE FROM %s WHERE %s=?'''%(table, primary_key),
                       (entry,))

    @cherrypy.expose
    def do_start_new_experiment(self, **kwargs):
        '''Process the "new experiment" form and start an experiment.'''
        def prepare_event(event, kwargs):
            arguments = list(inspect.signature(event.__init__).parameters)[1:]
            name = event.__name__
            prepared_kwargs = {a: kwargs['%s_%s'%(event.__name__,a)]
                               for a in arguments}
            return event(**prepared_kwargs)
        prepared_events = [prepare_event(e, kwargs) for e in events
                           if e.__name__+'__check' in kwargs]
        from scheduler import s, StartExperiment
        start = StartExperiment(**kwargs)
        start()
        for e in prepared_events:
            s.enter(0,0,e)
        return t_main.format(HTMLmain_article='<h1>New Experiment Started!</h1>')

    @cherrypy.expose
    def do_add_note(self, note, experiment_name):
        '''Add a note to a given experiment.'''
        with db:
            db.execute('''INSERT INTO notes (experiment_name, note)
                          VALUES (?, ?)''',
                       (experiment_name, note))
        # TODO add it with js instead of refreshing
        raise HTTPRedirect(cherrypy.request.headers['Referer'])


###############################################################################
# Configure the server with proper access to ports and static content files.
###############################################################################

cherrypy.config.update({'server.socket_host': '127.0.0.1',
                        'server.socket_port': 8080,
                        'tools.encode.on'   : True,
                        'tools.encode.encoding': 'utf-8',
                        'engine.autoreload.on': False,
                        'request.show_tracebacks': True,
                        'request.show_mismatched_params': True,
                        'log.screen': False,
                        'log.access_file': '',
                        'log.error_file': ''
                       })

pwd = os.path.dirname(os.path.realpath(__file__))
conf = {'/web_resources': {'tools.staticdir.on': True,
                           'tools.staticdir.dir': os.path.join(pwd, 'web_resources')
                          },
       }

root = Root()
cherrypy.tree.mount(root=root, config=conf)

def start_web_interface_thread():
    '''Start the web server in a dedicated thread. Return thread handler.'''
    cherrypy.engine.start()
    t = threading.Thread(target=cherrypy.engine.block,
                         name='WebInterface')
    t.start()
    return t

def stop_web_interface_thread():
    '''Stop the web server thread.'''
    cherrypy.engine.exit()
