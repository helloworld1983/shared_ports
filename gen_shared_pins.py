import csv
import re
import itertools

try:
    import datetime
    import getpass

    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    author = getpass.getuser()

except:
    date = ""
    author = ""


# ---------------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------------
module_name = 'shared_pins'  # systemverilog module name
inp_file = 'example_table.csv'  # configuration table file
out_file = module_name + '.sv'  # generated systemverilog file name

# Number of header lines
head_lines = 7

# Column numbers
name_col = 0  # external port names column
func_columns = [2, 4, 6, 8]  # function columns
func_dir_columns = [3, 5, 7, 9]  # direction columns

# ---------------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------------
internal_o_templ = '	input        {bus}{name}_o,\n'
internal_oe_templ = '	input        {bus}{name}_oe,\n'
internal_i_templ = '	output logic {bus}{name}_i,\n'
bus_templ = '[{}:{}] '

peripheral_port_templ = '''\
	output logic {bus}{name}_o,
	output logic {bus}{name}_oe,
	input        {bus}{name}_i,
'''

mux_control_templ = '''
	assign {o}  = matr_o[{num}][~port_mode[{num}]]; 
	assign {oe} = matr_oe[{num}][~port_mode[{num}]]; 
'''

connect_default_templ = '''\
		{i} = {default};
'''

connect_matr_templ = '''\
		matr_o[{num}] = {{{o_connections}}};
		matr_oe[{num}] = {{{oe_connections}}};
{matr_ie}
'''

matr_ie_templ = '''\
		if(matr_ie[{psig_num}][{isig_num}]) {isig_i} = {psig_i};
'''

# ---------------------------------------------------------------------------------
# read csv table
# ---------------------------------------------------------------------------------


def read_table(file, head_lines=0):
    with open(file, newline='') as f:
        table = csv.reader(f, delimiter=';', skipinitialspace=True)

        # skip header
        for i in range(head_lines):
            next(table, None)

        isig_list = []
        psig_list = []
        psig_num = 0

        # handle each row in table
        for row in table:
            # parse external port names
            signal = re.findall(r'([\w\d]+)', row[name_col])  # find name and if exist -- bit number

            psig = {
                'name': signal[0],
                'bit': None if len(signal) == 1 else signal[1],
                'connections': [],
                'num': psig_num
            }
            psig_num += 1

            psig['i'] = '{name}_i[{bit}]'.format(**psig) if psig['bit'] is not None else psig['name']+'_i'
            psig['o'] = '{name}_o[{bit}]'.format(**psig) if psig['bit'] is not None else psig['name']+'_o'
            psig['oe'] = '{name}_oe[{bit}]'.format(**psig) if psig['bit'] is not None else psig['name']+'_oe'

            for i in range(len(func_columns)):

                isig_fullname = re.findall(r'([\w\d]+)', row[func_columns[i]])

                if len(isig_fullname) > 0:
                    isig = {
                        'name': isig_fullname[0],
                        'bit': None if len(isig_fullname) < 2 else isig_fullname[1],
                        'direction': row[func_dir_columns[i]],
                        'default': 0,
                    }

                    isig['i'] = '{name}_i[{bit}]'.format(**isig) if isig['bit'] is not None else isig['name']+'_i'
                    isig['o'] = '{name}_o[{bit}]'.format(**isig) if isig['bit'] is not None else isig['name']+'_o'
                    isig['oe'] = '{name}_oe[{bit}]'.format(**isig) if isig['bit'] is not None else isig['name']+'_oe'

                    # rewrite oe with constant if pin is not bidirectional
                    if isig['direction'] not in ['io','oi','io1','oi1']:
                        if isig['direction'] in ['i','i1'] : 
                            isig['o'] = "1'b0"
                            isig['oe'] = "1'b0"
                        else:
                            isig['i'] = None
                            isig['oe'] = "1'b1"

                    if isig['direction'][-1] == '1':
                        isig['default'] = 1

                    # check if it is already in a list
                    if isig not in isig_list:
                        isig_list.append(isig)

                    psig['connections'].append(isig)
                else:
                    psig['connections'].append(None)

            psig_list.append(psig)

        return psig_list, sorted(isig_list,key=lambda k: k['name'])


def create_bus(signals):


    def ranges(i):
        for a, b in itertools.groupby(enumerate(i), lambda x: x[0]-x[1]):
            b = list(b)
            yield b[0][1], b[-1][1]

            
    bus = {}
    # make dict with all bits in a buses
    for sig in signals:
        if sig['bit'] is None:
            bus[sig['name']] = None
        elif sig['name'] in bus:
            bus[sig['name']].append(int(sig['bit']))
        else:
            bus[sig['name']] = [int(sig['bit'])]

    # compress bits numbers into bits ranges
    for sig in bus:
        if bus[sig] is not None:
            bus[sig] = list(ranges(set(bus[sig])))

    return bus


def count_buses(buses):
    bus_num = 0
    for bus in buses:
        if buses[bus] is not None:
            for subbus in buses[bus]:
                if subbus[0]!=subbus[1]:
                    bus_num += 1

    return bus_num


def main():
    # ------------------------------------------------------------------------------------
    # read configuration table
    # ------------------------------------------------------------------------------------
    psig_list, isig_list = read_table(inp_file, head_lines)

    # ------------------------------------------------------------------------------------
    # generate parts of output file
    # ------------------------------------------------------------------------------------
    mux_control = ""
    for signal in psig_list:
        mux_control += mux_control_templ.format(**signal)

    connect_default = ""
    for signal in isig_list:
        if signal['i'] is not None:
            connect_default += connect_default_templ.format(**signal)

    connect_matr = ""

    def conn(item, field):  # to do: make it one-line
        if item is None:
            return "1'b0"
        else:
            return item[field]

    for p in psig_list:
        matr_ie = ""
        for i in p['connections']:
            if i is not None and i['i'] is not None:
                matr_ie += matr_ie_templ.format(isig_i=i['i'],isig_num=p['connections'].index(i),psig_i=p['i'],psig_num=p['num'])

        p['oe_connections'] = ', '.join([conn(x, 'oe') for x in p['connections']])
        p['o_connections'] = ', '.join([conn(x, 'o') for x in p['connections']])
        connect_matr += connect_matr_templ.format(matr_ie=matr_ie,**p)


    peripheral_signals = ""
    psig_buses = create_bus(psig_list)
    
    for bus in psig_buses:
        if psig_buses[bus] is None:
            peripheral_signals += peripheral_port_templ.format(name=bus,bus="")
        else:
            for sub_range in psig_buses[bus]:
                peripheral_signals += peripheral_port_templ.format(name=bus,bus=bus_templ.format(sub_range[1], sub_range[0]))

    internal_signals = ""
    isig_buses = create_bus(isig_list)
    for bus in isig_buses:
        o_gen = False
        i_gen = False
        for i in isig_list:
            if bus is i['name']:
                if i['direction'] in ['io','oi','io1','oi1','o']:
                    o_gen = True
                if i['direction'] in ['io','oi','io1','oi1','i','i1']:
                    i_gen = True

        if isig_buses[bus] is None:
            if o_gen:
                internal_signals += internal_o_templ.format(name=bus, bus="")
            if o_gen and i_gen:
                internal_signals += internal_oe_templ.format(name=bus, bus="")
            if i_gen:
                internal_signals += internal_i_templ.format(name=bus, bus="")
        else:
            for sub_range in isig_buses[bus]:
                if o_gen:
                    internal_signals += internal_o_templ.format(name=bus,bus=bus_templ.format(sub_range[1],sub_range[0]))
                if o_gen and i_gen:
                    internal_signals += internal_oe_templ.format(name=bus,bus=bus_templ.format(sub_range[1],sub_range[0]))
                if i_gen:
                    internal_signals += internal_i_templ.format(name=bus,bus=bus_templ.format(sub_range[1],sub_range[0]))

    # ------------------------------------------------------------------------------------
    # generate output file 
    # ------------------------------------------------------------------------------------

    # number of control apb registers
    psignal_max = len(psig_list)-1

    with open('gen_shared_pins_template.txt','r') as template:
        
        print('Generating source file...')
        print('{} peripherial signals recognised, {} bus(es)'.format(len(psig_list),count_buses(psig_buses)))
        print('{} internal signals recognised, {} bus(es)'.format(len(isig_list),count_buses(isig_buses)))

        result = template.read().format(
            date=date,
            author=author,
            module_name=module_name,
            internal_signals=internal_signals,
            peripheral_signals=peripheral_signals, 
            psignal_max=psignal_max,
            regs_clog2_max=psignal_max.bit_length()+1, # +1 because the least significant bit of paddr is 2
            isignal_max=len(func_columns)-1, 
            isignal_clog2_max=(len(func_columns)-1).bit_length()-1, 
            mux_control=mux_control,
            connect_default=connect_default,
            connect_matr=connect_matr)
        with open(out_file,'w') as out:
            out.write(result)
        print('Done!')


if __name__ == '__main__':
    main()
