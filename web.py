import collections
import datetime
import html
import inspect
import logging
import time
import threading
import os.path

import cherrypy

from database import db
from dataprocessing import possible_plots, read_all_plottypes
from plotting import full_plot_html
from scheduler import events, current_experiment, reactor_scheduler, StartExperiment

logger = logging.getLogger('webinterface')

###############################################################################
# HTML Template class based on `str` that can escape HTML strings.
###############################################################################
# XXX Should have used actuall templating library. This is fairly ugly.
class Template(str):
    '''HTML escape all strings in `format` except keyword arguments starting with "HTML".'''
    def format(self, *args, **kwargs): # XXX Fancy formaters (everything except `str`) is not protected.
        args = (html.escape(_) if isinstance(_, str) else _
                for _ in args)
        kwargs = {k: html.escape(_) if (isinstance(_, str) and not k.startswith('HTML')) else _
                  for k, _ in kwargs.items()}
        return super().format(*args, **kwargs)
    def format_map(self, kwargs): # XXX Containers like defaultdict are not fully protected here.
        for k, v in kwargs.items():
            if (isinstance(v, str) and not k.startswith('HTML')):
                kwargs[k] = html.escape(v)
        return super().format_map(kwargs)


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
</head>
<body>
<div id="dark_layer"><h1>Refreshing Page</h1></div>
<nav class="pure-menu pure-menu-horizontal">
    <span id="timertext">Refresh in <span id="timer"></span>.</span>
    <a href="#" class="pure-menu-heading pure-menu-link">RPB</a>
    <ul class="pure-menu-list">
        <li class="pure-menu-item"><a href="/"        class="pure-menu-link">Status</a></li>
        <li class="pure-menu-item"><a href="/new"     class="pure-menu-link">New Experiment</a></li>
        <li class="pure-menu-item"><a href="/archive" class="pure-menu-link">Archive</a></li>
        <li class="pure-menu-item"><a href="/strains" class="pure-menu-link">Strains</a></li>
        <li class="pure-menu-item"><a href="/strain"  class="pure-menu-link">New Strain</a></li>
    </ul>
    <script>reloadTimeout();</script>
</nav>
<article class="pure-g">
<div class="pure-u-1">
{HTMLmain_article}
</div>
</article>
<footer>
Built with cherrypy, sqlite, bokeh, purecss, and more on Arduino and Raspberry Pi by Hegarty, Krastanov, and Racharaks.
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
            <input id="name" name="name" type="text" placeholder="" class="pure-input-1-4">
        </div>

        <div class="pure-control-group">
            <label for="strain">Strain</label>
            <select id="strain" name="strain" type="text" placeholder="" class="pure-input-1-4">
            {HTMLstrainoptions}
            </select>
        </div>

        <div class="pure-control-group">
            <label for="temp">Initial Temperature</label>
            <input id="temp" name="temp" type="text" placeholder="" class="pure-input-1-4">
        </div>

        <div class="pure-control-group">
            <label for="light">Initial Light Levels</label>
            <input id="light" name="light" type="text" placeholder="" class="pure-input-1-4">
        </div>

        <div class="pure-control-group">
            <label for="description">Description</label>
            <textarea id="description" name="description" placeholder="" class="pure-input-1-4"></textarea>
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
        <div>{HTMLeventbuttons}</div>
        {HTMLevents}
    </fieldset>

    <button type="submit" class="pure-button pure-button-primary">Start Experiment</button>
</form>
''')

# Template for the configuration for a single event type.
t_new_event = Template('''
<div id="{event_name}" style="display:none;">
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
    <input id="{event_name}_{arg}" name="{event_name}_{arg}" placeholder="" type="text" value="{default}">
</div>
''')

# Template for the buttons toggling the event's availability.
t_new_event_button = Template('''<button type="button" class="pure-button pure-u-1-6" onClick="toggleEventInput(this, '{event_name}');">{event_name}</button>''')

def format_event_arguments(event):
    '''Given an event, return a form with all arguments for that event.'''
    aspec = inspect.getargspec(event.__init__)
    arguments = zip(aspec.args[-len(aspec.defaults):],aspec.defaults)
    arguments_html='\n'.join([t_new_event_args.format(
                                event_name=event.__name__,
                                arg=arg,
                                default=default)
                              for arg,default in arguments])
    return arguments_html

def format_new_html():
    '''Create a configuration page for the setup of a new experiment.'''
    events_html='\n'.join([t_new_event.format(
                             event_name=e.__name__,
                             event_description=e.__doc__,
                             HTMLevent_arguments=format_event_arguments(e))
                           for e in events])
    eventbuttons_html=' '.join([t_new_event_button.format(event_name=e.__name__) for e in events])
    with db:
        strainoptions_html=''.join('''<option value="{name}">{name}</option>'''.format(**r)
                                   for r in db.execute('SELECT name FROM strains ORDER BY name ASC'))
    return t_main.format(HTMLmain_article=t_new.format(HTMLevents=events_html,
                                                       HTMLeventbuttons=eventbuttons_html,
                                                       HTMLstrainoptions=strainoptions_html))


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
        <dd class="list_strain"><a href="/strain/{strain_name}">{strain_name}</a></dd>
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
<div class="notes_container">
<h4>Notes</h4>
<div class="list_notes max-height-scroll">
<form class="pure-form">
    <textarea class="pure-input-1" name="note"></textarea>
    <input type="hidden" value="{experiment_name}" name="experiment_name">
    <button type="button" onClick="addAndRefreshContainer(this);" class="button-xsmall pure-button pure-button-primary pure-input-1">Add Note</button>
</form>
<ul class="boxed-list">
{HTMLnotes}
</ul>
</div>
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
    '''Prepare an AJAX-ish list of all notes for a given experiment.'''
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
<link rel="stylesheet" href="/web_resources/bokeh.0.12.0.min.css">
<div class="pure-g">
<div class="pure-u-3-4">
<form class="pure-form">
<div class="pure-g">
{HTMLlinks}
</div>
</form>
<script src="/web_resources/bokeh.0.12.0.min.js"></script>
<div id="bokeh_plot">
<div class="loader"></div> Plot is loading...
</div>
</div>
<div class="pure-u-1-4">
<form class="pure-form">
<fieldset class="pure-group">
<a class="pure-input-1 pure-button pure-button-primary" href="/table/{name}">View Table</a>
<a class="pure-input-1 pure-button pure-button-primary" href="/downloadcsv/{name}?interpolate=False">Download CSV</a>
<a class="pure-input-1 pure-button pure-button-primary" href="/downloadcsv/{name}?interpolate=True">Download CSV (interpolated)</a>
</fieldset>
</form>
<h4>Strain</h4>
<div>
<a href="/strain/{strain_name}">{strain_name}</a>
</div>
<h4>Description</h4>
<div class="list_notes max-height-scroll">
{description}
</div>
{HTMLnotes}
</div>
</div>
''')

def format_experiment_html(experiment):
    '''Load all data for a given experiment, make bokeh plots, and load in the HTML template.'''
    links = '\n'.join('''<div class="pure-u-1-5"><a class="pure-input-1 pure-button" href="/experiment/{experiment}/{plot_type}">{plot_type}</a></div>
                      '''.format(experiment=experiment,
                                 plot_type=p)
                      for p in possible_plots.keys())
    with db:
        query = db.execute('''SELECT * FROM experiments WHERE name=?''',
                           (experiment,))
        r = query.fetchone()
    return t_main.format(HTMLmain_article=t_experiment.format(
        HTMLlinks=links,
        HTMLnotes=format_notes_html(experiment),
        **r
        ))


###############################################################################
# The current experiment status template.
###############################################################################

t_status = Template('''
<h1>Current Status</h1>
<div class="pure-g">
<div class="pure-u-1"><a class="pure-button button-error" href="/stop">Stop</a></div>
<div class="pure-u-1"><a href="/experiment/{experiment_name}">{experiment_name}</a> (<a href="/strain/{strain}">{strain}</a>): {description}</div>
<div class="pure-u-3-4">plots</div>
<div class="pure-u-1-4">
    <div id="schedule">
        {HTMLschedule}
    </div>
    <script>trackSchedule();</script>
    <hr>
    <div>{HTMLnotes}</div>
</div>
</div>
''')

# Templare for the schedule board.
t_schedule = Template('''
        <h4>Schedule</h4>
        <div class="list_notes max-height-scroll">
        <ul class="boxed-list">
        {HTMLevents}
        </ul>
        </div>
''')

# Template for presenting an event.
t_event = Template('''
<li class="event" data-priority="{event.priority}" data-waiting="{waiting}">
{event.action.__class__.__name__}<span> in <time data-seconds="{time}"></time></span>
</li>
''')

def format_schedule_html():
    '''Create an HTML tree for the current schedule.'''
    events_html = '\n'.join(t_event.format(event=e,
                                           time=e.time-time.monotonic(),
                                           waiting = 0 if e.time-time.monotonic()>0 else 1)
                            for e in reactor_scheduler.queue)
    current_html = '<li class="event current-event">{0.action.__class__.__name__}<span> currently</span><div class="loader"></div></li>'.format(s.current) if s.current else ''
    events_html = current_html+events_html
    return t_schedule.format(HTMLevents=events_html)

def format_status_html():
    '''Create a status page for the current experiment.'''
    if current_experiment is None:
        return t_main.format(HTMLmain_article='<h1>No Experiments Running</h1>')
    logger.info('Generating status page for experiment %s...', current_experiment)
    with db:
        c = db.execute('''SELECT strain_name, description FROM experiments
                       WHERE name=?''',
                       (current_experiment,))
        strain, description = c.fetchone()
    return t_main.format(HTMLmain_article=t_status.format(experiment_name=current_experiment,
                                                          strain=strain,
                                                          description=description,
                                                          HTMLschedule=format_schedule_html(),
                                                          HTMLnotes=format_notes_html(current_experiment)))


###############################################################################
# The list of strains template.
###############################################################################

t_strains = Template('''
<h1>Strains</h1>
<script src="/web_resources/list.1.2.0.min.js"></script>
<div id='strains'>
<div>
    <form class="pure-form">
    <fieldset>
    <legend>Search strains:</legend>
    <input class="list_search" placeholder="Search">
    </fieldset>
    </form>
</div>
<ul class='list_list boxed-list'>
{HTMLstrains_entries}
</ul>
</div>
<script>
var options = {{
  valueNames: [ 'list_name', 'list_description' ],
  listClass: 'list_list',
  searchClass: 'list_search'
}};

var strainsList = new List('strains', options);
</script>
<script src="/web_resources/ASCIIMathML.2.2.js"></script>
''')

# A template for an entry in the list of strains.
t_strains_entry = Template('''
<li class="pure-g fixed-height-block" id="strains_{name}">
    <div class="pure-u-11-12">
        <h3 class="list_name"><a href="/strain/{name}">{name}</a></h3>
    </div>
    <div class="pure-u-1-12">
        <button class="button-trash pure-button" onClick="deleteNearestLI(this);"><i class="fa fa-trash"></i></button>
    </div>
    <div class="pure-u-1-3">
        <h4>Description</h4>
        <div class="list_description max-height-scroll">{description}</div>
    </div>
    <div class="pure-u-2-3">
        <h4>Formulae</h4>
        <div class="list_formulae max-height-scroll">
        <dl>
            <dt>Output/Input Light Intensity Ratio to Optical Density:</dt>
            <dd>`color(black)({light_ratio_to_od_formula})`</dd>
            <dt>Optical Density to Biomass</dt>
            <dd>`color(black)({od_to_biomass_formula})`</dd>
            <dt>Optical Density to Cell Count</dt>
            <dd>`color(black)({od_to_cell_count_formula})`</dd>
        </dl>
        </div>
    </div>
</li>
''')

def format_strains_html():
    '''Load all strains from the database and list them in the HTML template.'''
    with db:
        translate_power_sign = lambda _: {k: _[k].replace('**', '^') if _[k] and k not in ('name', 'description') else _[k]
                                          for k in _.keys()}
        entries = '\n'.join(t_strains_entry.format(**translate_power_sign(r))
                            for r in db.execute('''SELECT * FROM strains
                                                   ORDER BY name ASC'''))
    return t_main.format(HTMLmain_article=t_strains.format(HTMLstrains_entries=entries))


###############################################################################
# Template for adding or editing a strain.
###############################################################################

t_addedit_strain = Template('''
<h1>Add or Edit a Strains</h1>
<form class="pure-form pure-form-aligned" method="POST" action="/do_addedit_strain">
    <fieldset>
        <legend>General</legend>
        <div class="pure-control-group">
            <label for="name">Strain Name<sup class="note">[1]</sup></label>
            <input id="name" name="name" type="text" placeholder="" value="{name}" class="pure-input-1-4">
        </div>

        <div class="pure-control-group">
            <label for="description">Description</label>
            <textarea id="description" name="description" placeholder="" class="pure-input-1-4">{description}</textarea>
        </div>
    <sup class="note">[1]: Change the name to create a new strain based on a previous one.</sup>
    </fieldset>

    <fieldset>
        <legend>Formulae</legend>
        <div class="pure-control-group">
            <label for="light_ratio_to_od_formula">Output/Input Light Intensity Ratio to Optical Density:</label>
            <input id="light_ratio_to_od_formula" name="light_ratio_to_od_formula" type="text" placeholder="" value="{light_ratio_to_od_formula}" class="pure-input-1-4">
        </div>
        <div class="pure-control-group">
            <label for="od_to_biomass_formula">Optical Density to Biomass</label>
            <input id="od_to_biomass_formula" name="od_to_biomass_formula" type="text" placeholder="" value="{od_to_biomass_formula}" class="pure-input-1-4">
        </div>
        <div class="pure-control-group">
            <label for="od_to_cell_count_formula">Optical Density to Cell Count</label>
            <input id="od_to_cell_count_formula" name="od_to_cell_count_formula" type="text" placeholder="" value="{od_to_cell_count_formula}" class="pure-input-1-4">
        </div>
    </fieldset>

    <div class="pure-controls">
        <button type="submit" class="pure-button pure-button-primary">Submit Changes</button>
    </div>
</form>
''')

def format_addedit_strain_html(strain=None):
    '''Load a strain in an edit page or show a "new strain" page.'''
    if strain:
        with db:
            c = db.execute('''SELECT * FROM strains WHERE name=?''', (strain,))
            strain = c.fetchone()
        return t_main.format(HTMLmain_article=t_addedit_strain.format(**strain))
    else:
        strain = collections.defaultdict(str)
        return t_main.format(HTMLmain_article=t_addedit_strain.format_map(strain))


###############################################################################
# Template for data tables.
###############################################################################

t_table = Template('''
<h1>Data Table with interpolated values</h1>
<h2>{experiment}</h2>
<form class="pure-form">
<div class="pure-g">
<div class="pure-u-1-4">
<a class="pure-input-1 pure-button pure-button-primary" href="/downloadcsv/{experiment}?interpolate=True">Download CSV (interpolated)</a>
</div>
<div class="pure-u-1-4">
<a class="pure-input-1 pure-button pure-button-primary" href="/downloadcsv/{experiment}?interpolate=False">Download CSV</a>
</div>
</div>
</form>
{HTMLtable}
''')

def format_table(experiment):
    '''Display a data table as HTML.'''
    table_html = read_all_plottypes(experiment, interpolate=True).to_html()
    return t_main.format(HTMLmain_article=t_table.format(experiment=experiment,
                                                         HTMLtable=table_html))


###############################################################################
# The UI server implementation.
###############################################################################

class Root:
    @cherrypy.expose
    def index(self):
        return format_status_html()

    @cherrypy.expose
    def schedule(self):
        return format_schedule_html()

    @cherrypy.expose
    def stop(self):
        if not any(isinstance(_.action, StopExperiment)
                   for _ in reactor_scheduler.queue):
            reactor_scheduler.enter(0,-1,StopExperiment())
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def archive(self):
        return format_archive_html()

    @cherrypy.expose
    def experiment(self, name):
        return format_experiment_html(name)

    @cherrypy.expose
    def experiment_full_plot(self, name, plot_type):
        return full_plot_html(experiment, plot_type)

    @cherrypy.expose
    def new(self):
        return format_new_html()

    @cherrypy.expose
    def strains(self):
        return format_strains_html()

    @cherrypy.expose
    def strain(self, strain=None):
        return format_addedit_strain_html(strain)

    @cherrypy.expose
    def table(self, experiment):
        return format_table(experiment)

    @cherrypy.expose
    def do_delete(self, table, entry):
        '''Delete an entry from a permitted table.'''
        ids = {'experiments': 'name',
               'strains'    : 'name',
               'notes'      : 'timestamp'}
        primary_key = ids[table]
        with db:
            db.execute('''DELETE FROM %s WHERE %s=?'''%(table, primary_key),
                       (entry,))

    @cherrypy.expose
    def do_start_new_experiment(self, **kwargs):
        '''Process the "new experiment" form and start an experiment.'''
        logger.info('Starting new experiment %s...', kwargs['name'])
        def prepare_event(event, kwargs):
            arguments = list(inspect.signature(event.__init__).parameters)[1:]
            name = event.__name__
            prepared_kwargs = {a: kwargs['%s_%s'%(event.__name__,a)]
                               for a in arguments}
            return event(**prepared_kwargs)
        start = StartExperiment(**kwargs)
        prepared_events = [prepare_event(e, kwargs) for e in events
                           if e.__name__+'__check' in kwargs]
        if not prepared_events:
            raise ValueError('No measurement events scheduled.')
        with db:
            to_record = [kwargs[_] for _ in ['name', 'description', 'strain', 'row1', 'row2', 'row3', 'row4', 'col1', 'col2', 'col3', 'col4', 'col5']]
            db.execute('''INSERT INTO experiments (name, description, strain_name, row1, row2, row3, row4, col1, col2, col3, col4, col5)
                          VALUES (?, ?, ?,  ?,?,?,?, ?,?,?,?,?)''',
                          to_record)
        reactor_scheduler.enter(0,-1,start)
        for e in prepared_events:
            reactor_scheduler.enter(0,0,e)
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def do_add_note(self, note, experiment_name):
        '''Add a note to a given experiment.'''
        with db:
            db.execute('''INSERT INTO notes (experiment_name, note)
                          VALUES (?, ?)''',
                       (experiment_name, note))
        return format_notes_html(experiment_name)

    @cherrypy.expose
    def do_addedit_strain(self, name, description, light_ratio_to_od_formula,
            od_to_biomass_formula, od_to_cell_count_formula):
        with db:
            db.execute('''UPDATE OR IGNORE strains
                          SET description=?,
                              light_ratio_to_od_formula=?,
                              od_to_biomass_formula=?,
                              od_to_cell_count_formula=?
                          WHERE name=?''',
                       (description, light_ratio_to_od_formula,
                        od_to_biomass_formula, od_to_cell_count_formula,
                        name))
            db.execute('''INSERT OR IGNORE INTO strains
                          (name, description,
                           light_ratio_to_od_formula,
                           od_to_biomass_formula,
                           od_to_cell_count_formula)
                          VALUES (?, ?, ?, ?, ?)''',
                       (name, description, light_ratio_to_od_formula,
                        od_to_biomass_formula, od_to_cell_count_formula))
        return t_main.format(HTMLmain_article='<h1>Strain Changes Commited!</h1>')


###############################################################################
# Configure the server with proper access to ports and static content files.
###############################################################################

def start_web_interface_thread():
    '''Start the web server in a dedicated thread. Return thread handler.'''
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

    from cherrypy.lib import cpstats
    cherrypy.config.update({'tools.cpstats.on': True})
    cherrypy.tree.mount(cpstats.StatsPage(), '/cpstats')

    cherrypy.engine.start()
    t = threading.Thread(target=cherrypy.engine.block,
                         name='WebInterface')
    t.start()
    return t

def stop_web_interface_thread():
    '''Stop the web server thread.'''
    cherrypy.engine.exit()
