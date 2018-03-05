"""A Python wrapper around ReChart charts.

See: recharts.org

All CamelCase names are convert to snake_case, for example:

    AreaChart -> area_chart
    CartesianGrid -> cartesian_grid

For example this React code:

    <LineChart width={600} height={300} data={data}
        margin={{top: 5, right: 30, left: 20, bottom: 5}}>
            <XAxis dataKey='name'/>
            <YAxis/>
            <CartesianGrid strokeDasharray='3 3'/>
            <Tooltip/>
            <Legend />
            <Line type='monotone' dataKey='pv' stroke='#8884d8' strokeDasharray='5 5'/>
            <Line type='monotone' dataKey='uv' stroke='#82ca9d' strokeDasharray='3 4 5 2'/>
    </LineChart>

Would become:

    line_chart = Chart(data, 'line_chart', width=600, height=300)
    line_chart.x_axis(data_key='name')
    line_chart.y_axis()
    line_chart.cartesian_grid(stroke_dasharray='3 3')
    line_chart.tooltip()
    line_chart.legend()
    line_chart.line(type='monotone', data_key='pv', stroke='#8884d8',
        stroke_dasharray='5 5')
    line_chart.line(type='monotone', data_key='uv', stroke='#82ca9d',
        stroke_dasharray='3 4 5 2')

Or, in builder notation:

    (Chart(data, 'line_chart', width=600, height=300)
        .x_axis(data_key='name')
        .y_axis()
        .cartesian_grid(stroke_dasharray='3 3')
        .tooltip()
        .legend()
        .line(type='monotone', data_key='pv', stroke='#8884d8',
            stroke_dasharray='5 5')
        .line(type='monotone', data_key='uv', stroke='#82ca9d',
            stroke_dasharray='3 4 5 2'))

Or, with syntax sugar type-specific builders:

    LineChart(data, width=600, height=300).x_axis(data_key='name')
    # These sugary builders already have all sorts of defaults set
    # so usually there's no need to call any additional methods on them :)

    LineChart(data, width=600, height=300)
    # You don't even need to specify data keys. These are selected automatically
    # for your from the data.
"""

import pandas as pd

from .ChartComponent import ChartComponent
from .caseconverters import to_upper_camel_case, to_lower_camel_case, to_snake_case
from .chartconfig import *
from streamlet.shared import data_frame_proto

current_module = __import__(__name__)

class Chart:
    def __init__(self, data, type, width=0, height=0, **kwargs):
        """Constructs a chart object.

        Args:
            type -- a string with the snake-case chart type. Example:
            'area_chart', 'bar_chart', etc...

            data -- a np.Array or pd.DataFrame containg the data to be plotted.
            Series are referenced by column name.

            width -- a number with the chart width. Defaults to 0, which means
            "the default width" rather than actually 0px.

            height -- a number with the chart height. Defaults to 0, which means
            "the default height" rather than actually 0px.

            kwargs -- keyword arguments of two types: (1) properties to be added
            to the ReChart's top-level element; (2) a special 'components'
            keyword that should point to an array of default ChartComponents to
            use, if desired.
        """
        assert type in CHART_TYPES_SNAKE, f'Did not recognize "{type}" type.'
        self._data = pd.DataFrame(data)
        self._type = type
        self._width = width
        self._height = height
        self._components = (
            kwargs.pop('components', [])
            or []  # In case kwargs['components'] is None.
        )
        self._props = [(str(k), str(v)) for (k,v) in kwargs.items()]

    def append_component(self, component_name, props):
        """Sets a chart component

        Args:
            component_name -- a snake-case string with the ReCharts component
            name.
            props -- the ReCharts component value.
        """
        self._components.append(ChartComponent(component_name, props))

    def marshall(self, proto_chart):
        """Loads this chart data into that proto_chart."""
        proto_chart.type = to_upper_camel_case(self._type)
        data_frame_proto.marshall_data_frame(self._data, proto_chart.data)
        proto_chart.width = self._width
        proto_chart.height = self._height

        self._append_missing_data_components()

        for component in self._components:
            proto_component = proto_chart.components.add()
            component.marshall(proto_component)

        for (key, value) in self._props:
            proto_prop = proto_chart.props.add()
            proto_prop.key = to_lower_camel_case(key)
            proto_prop.value = value

    def _append_missing_data_components(self):
        """Appends all required data components that have not been specified.

        Required axes are specified in the REQUIRED_COMPONENTS dict, which
        points each chart type to a tuple of all components that are required
        for that chart. Required components themselves are either normal tuples
        or a repeated tuple (specified via ForEachColumn), and their children
        can use special identifiers such as ColumnAtIndex, ColumnAtCurrentIndex,
        and ValueCycler.
        """
        missing_required_components = REQUIRED_COMPONENTS.get(self._type, None)

        if missing_required_components is None:
            return

        existing_component_names = set(c.type for c in self._components)

        for missing_required_component in missing_required_components:

            if type(missing_required_component) is ForEachColumn:
                numRepeats = len(self._data.columns)
                comp_name, comp_value = missing_required_component.prop
            else:
                numRepeats = 1
                comp_name, comp_value = missing_required_component

            if comp_name in existing_component_names:
                continue

            for i in range(numRepeats):
                if type(comp_value) is dict:
                    props = {
                        k: self._materializeValue(v, i)
                        for (k, v) in comp_value.items()
                    }
                    self.append_component(comp_name, props)

                else:
                    props = self._materializeValue(comp_value, i)
                    self.append_component(comp_name, props)

    def _materializeValue(self, value, currCycle):
        """Replaces ColumnAtIndex with a column name if needed.

        Args:
            value -- anything. If value is a ColumnAtIndex or
            ColumnAtCurrentIndex then it gets replaces with a column name. If
            ValueCycler, it returns the current item in the cycler's list. If
            it's anything else, it just passes through.

            currCycle -- an integer. For repeated fields (denoted via
            ForEachColumn) this is the number of the current column.
        """
        if type(value) is ColumnAtIndex:
            index = value.index

        elif type(value) is ColumnAtCurrentIndex:
            index = currCycle

        elif type(value) is ValueCycler:
            return value.get(currCycle)

        else:
            return value

        if index >= len(self._data.columns):
            raise IndexError('Index {} out of bounds'.format(index))

        return self._data.columns[index]


def register_type_builder(chart_type, short_name=None):
    """Adds a builder function to this module, to build specific chart types.

    These sugary builders also set up some nice defaults from the
    DEFAULT_COMPONENTS dict, that can be overriden after the instance is built.

    Args:
        chart_type -- A string with the snake-case name of the chart type to add.

        short_name -- If desired, a string containing the name of the class method
        to be added. This is used to add methods like foo() for annoying-to-type
        chart types such as 'foo_chart' (instead of foo_chart()).
    """
    chart_type_snake = to_snake_case(chart_type)

    def type_builder(data, **kwargs):
        kwargs.pop('type', None)  # Ignore 'type' key from kwargs, if exists.
        components = DEFAULT_COMPONENTS.get(chart_type_snake, {})
        return Chart(data, type=chart_type_snake,
                     components=components, **kwargs)

    setattr(current_module, short_name or chart_type, type_builder)

def register_component(component_name, implemented):
    """Adds a method to the Chart class, to set the given component.

    Args:
        component_name -- A snake-case string containing the name of a chart
        component accepted by ReCharts.

        implemented -- a boolean that is true/false depending on whether Streamlit
        supports the given component_name or not.

    Example:
        register_component('foo_bar')
        c = Chart(myData, 'line_chart')
        c.foo_bar(stuff='other stuff', etc='you get the gist')

    In addition, the methods created by this function return the Chart
    instance for builder-style chaining:

        register_component('baz')
        c = Chart(myData, 'line_chart').foo_bar(stuff='yes!').baz()
    """
    def append_component_method(self, **props):
        if implemented:
            self.append_component(component_name, props)
        else:
            raise NotImplementedError(component_name + ' not implemented.')
        return self  # For builder-style chaining.

    setattr(Chart, component_name, append_component_method)

# Add syntax-sugar builder methods to the Chart class, to allow us to do things
# like Chart.foo(data) instead of Chart(data, 'foo').
for chart_type in CHART_TYPES:
    register_type_builder(chart_type)

# Add methods to Chart class, for each component in CHART_COMPONENTS.
for component_name, implemented in CHART_COMPONENTS.items():
    register_component(to_snake_case(component_name), implemented)
