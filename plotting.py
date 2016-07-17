from bokeh.embed import components
from bokeh.layouts import gridplot
from bokeh.models import ColumnDataSource, Range1d, Rect, HoverTool
from bokeh.plotting import figure

from dataprocessing import possible_plots, read_plottype, read_experiment, read_all_plottypes


def full_plot(experiment, plot_type):
    '''Generate a bokeh plot for a given experiment/plot combination.'''
    plot_type = possible_plots[plot_type]

    # Prepare the data.
    df = read_plottype(experiment, plot_type)
    ds = ColumnDataSource(df)

    # Summary plot (average over all wells).
    tools = 'pan,wheel_zoom,box_zoom,reset,resize,crosshair'
    webgl = False
    bottom = min(df['min'].min(), plot_type.min)
    top    = max(df['max'].max(), plot_type.max)
    left   = df.index.min()
    right  = df.index.max()
    range_y = Range1d(bottom, top)
    range_x = Range1d(left, right)
    p_mean = figure(width=350, height=350, x_axis_type='datetime',
		    toolbar_location=None, tools=tools,
                    x_range=range_x, y_range=range_y,
                    webgl=webgl)
    p_mean.line(source=ds, x='timestamp', y='median', color='black', legend='median', line_width=2)
    p_mean.line(source=ds, x='timestamp', y='max', color='red',   legend='max',  line_width=2)
    p_mean.line(source=ds, x='timestamp', y='min', color='blue',  legend='min',  line_width=2)
    p_mean.border_fill_color = "white"
    p_mean.legend.background_fill_alpha = 0.5

    # Add hover notes to the summary plot.
    notes = read_experiment(experiment, 'notes')
    notes['str_date'] = notes.index.map(lambda _:_.strftime('%Y-%m-%d %H:%M:%S'))
    notes_ds = ColumnDataSource(notes)
    box = Rect(height=top-bottom,
               width=(df.index.max()-df.index.min()).total_seconds()*1e3/20+30*60*1e3,
               x='timestamp',
               y=(top+bottom)/2,
               fill_color='red', fill_alpha=0.2, line_color='red', line_alpha=0.6)
    box_r = p_mean.add_glyph(source_or_glyph=notes_ds, glyph=box)
    box_hover = HoverTool(renderers=[box_r], tooltips='<div style="width:100px;"><h4 style="font-size:0.5em;margin:1px;padding:1px;">@str_date</h4><p style="font-size:0.5em;margin:1px;padding:1px;">@note</p></div>')
    p_mean.add_tools(box_hover)

    # Grid plots (small plots, one for each well).
    plots = []
    for r in range(1,5):
        cols = []
        for c in range(1,6):
            p = figure(width=100, height=100, x_axis_type='datetime',
        	       min_border_top=2, min_border_right=2,
        	       min_border_bottom=20, min_border_left=20,
        	       toolbar_location=None,
        	       tools=tools,
        	       x_range=range_x, y_range=range_y,
                       webgl=webgl)
            p.line(source=ds, x='timestamp', y='%s%s'%(r,c))
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
    for r in range(1,5):
        p_rows.line(source=ds, x='timestamp', y='r%d'%r, color=colors[r-1], legend='row %d'%r, line_width=2)
    p_rows.legend.background_fill_alpha = 0.5

    # Column plots (one line per column of wells).
    p_cols = figure(width=500, height=350, x_axis_type='datetime',
		    toolbar_location=None, tools=tools,
		    x_range=range_x, y_range=range_y,
                    webgl=webgl)
    for c in range(1,6):
        p_cols.line(source=ds, x='timestamp', y='c%d'%c, color=colors[c-1], legend='col %d'%c, line_width=2)
    p_cols.legend.background_fill_alpha = 0.5

    # Final layout and html generation.
    final_plot = gridplot([[p_mean, p_cols], [p_rows, p_wells]])
    return final_plot


def full_plot_html(experiment, plot_type):
    final_plot = full_plot(experiment, plot_type)
    bokeh_script, bokeh_div = components(final_plot)
    return bokeh_div+'\n'+bokeh_script
