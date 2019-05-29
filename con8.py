# !/usr/bin/python
import os
import re
import sys
import logging
import argparse
import json
import yaml
import builtins
from subprocess import run, PIPE
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger('configur8')
LOGGER.setLevel(logging.WARNING)

def possible_abort(e, fail_on_error):        
    LOGGER.error(e)
    if fail_on_error:
        if os.environ.get('SHOWSTACKS'):
            raise Error(e)
        else:
            sys.exit(8)
    else:
        print('WARNING: Exception occured but suppressed:' %e)

def handle_outputformat(args, result):
    if args.outputformat == 'yaml':
        output = yaml.dump(result)
    elif args.outputformat == 'json':
        output = json.dumps(result, sort_keys=True, indent=2)
    else:
        print('Unknown outputformat %s' %args.outputformat)
        sys.exit(8)        
    return output

class Error(BaseException): 

    def __init__(self, message):
        pass

class ConfigValue:    

    def __repr__(self):
        return self.__str_full__()

    def __str_full__(self):
        return json.dumps({
            'origin': self.origin,
            'name': self.name,
            'value': self.value,
            'substitute': self.substitute,
            'enabled': self.enabled            
        }, sort_keys=True, indent=2)
    
    def __str__(self):
        return self.value
    
    def __init__(self, name, value):     
        self.origin = ''   
        self.name = name
        self.value = value
        self.substitute = True        
        self.enabled = True        

class ConfigReader:

    files = []
    values = {}

    def read_file(self, file):
            with open(file, 'rb') as ifile:
                return ifile.read()

    def handle_list(self, data, file=None):
        """
        handle json object format
        {
          "key": "some_key",
          "value": "some value",
          "_enabled": true,          
          "_substitute": true   
        }
        """
        for key_def in data:            
            config_obj = ConfigValue(key_def['key'], key_def['value'])
            config_obj.origin = file
            config_obj.substitute = key_def.get('_substitute', True)
            config_obj.enabled = key_def.get('_enabled', True)            
            if config_obj.enabled:           
                self.values[config_obj.name] = config_obj

    def handle_props(self, data, file=None):
        """
        handle json property format
        {
          "key1": "some value",
          "key1._enabled": true          
        }
        """

        def is_metadata(key):
            last_d = key.split('.')[-1]
            return last_d.startswith('_')

        def create_object(key, data):
            config_obj = ConfigValue(key, data.get(key))
            config_obj.origin = file
            config_obj.substitute = data.get('%s._substitute' %key, True)
            config_obj.enabled = data.get('%s_enabled' %key, True)            
            return config_obj

        keys = data.keys()
        for key in keys:
            if not is_metadata(key):
                obj = create_object(key, data)
                if obj.enabled:
                    self.values[key] = obj

    def read_keys(self, file):
        _, extension = os.path.splitext(file)
        data = None
        try:
            if extension == '.json':            
                data = json.loads(self.read_file(file))                                    
            if extension in ['.yaml', '.yml']:            
                data = yaml.safe_load(self.read_file(file))                 
        except Exception as e:
            LOGGER.error(e)
        # in case we get key as an object - with metavariables
        if isinstance(data, list):                
            self.handle_list(data, file=file)
        # in case we get key as plain dict
        else:
            self.handle_props(data, file=file)

    def gather_facts(self, path, return_value, *args, **nargs):    
        # TODO: handle file vs path (possibility to specify a certain file)
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:            
                _, extension = os.path.splitext(name)
                if extension in ['.yaml','.yml','.json']:
                    return_value.append(os.path.join(root, name))
            for dirname in dirs:
                self.gather_facts(dirname, return_value, *args, **nargs) 
        return return_value

    def __init__(self, pathnames, config={}):
        self.files = []
        self.config = config
        for pathname in pathnames:
            self.files.extend(self.gather_facts(pathname[0], []))
            for file in self.files:
                self.read_keys(file)

class ConfigResolver:

    KEY_IDENTIFIER_RE = re.compile('.*(?<!\\\\)\$\{([\w\.\(\'\"\,\,\-)]+)\}.*')
    FUNCTION_IDENTIFIER_RE = re.compile('.*(?<!\\\\)\$\(([\\\\\w\.\-\(\"\' \,\)\[\]\:,\-\+]+)\).*')
    SCRIPT_IDENTIFIER_RE = re.compile('.*(?<!\\\\)\$\[(\w+):([\\\\\w\.\-\(\"\' \,\)\[\]\:,\-\s]*)\].*')
    RE_NAME = re.compile('^[a-zA-Z0-9_\-]+$')

    # create a list of save local functions to use
    safe_list = ['math','acos', 'asin', 'atan', 'atan2', 'ceil', 'cos', 'cosh', 
    'degrees', 'e', 'exp', 'fabs', 'floor', 'fmod', 'frexp', 'hypot', 'ldexp', 'log', 
    'log10', 'modf', 'pi', 'pow', 'radians', 'sin', 'sinh', 'sqrt', 'tan', 'tanh']
    #use the list to filter the local namespace
    safe_dict = dict([ (k, locals().get(k, None)) for k in safe_list ])    
    # dict for external scripts and their shortrefs
    script_dict = {}

    def _resolve_key(self, key, level=0, key_nesting=[], fail_on_error=True):
        
        def handle_string(key, done):
            """
            handle strings and json strings ${}
            """            
            keys_to_resolve = re.findall(self.KEY_IDENTIFIER_RE, str(key.value))
            done = len(keys_to_resolve) == 0
            if not done:
                LOGGER.debug('%s>>> resolving %s (%s) -> %s' % (level, key.name, key.value, keys_to_resolve))
                key_nesting.append(key.name)
                for match_group_key in keys_to_resolve:
                    if match_group_key in key_nesting[1:]:                        
                        possible_abort("Key %s cant be resolved, cyclic dependency found %s" %(key.name, '->'.join(key_nesting)), fail_on_error)
                    value = self._resolve_key(self.key_set.get(match_group_key), level+1, key_nesting=key_nesting)
                    if value != None:
                        key.value = key.value.replace('${%s}' % match_group_key, str(value))
                    elif not fail_on_error:
                        key.value = key.value.replace('${%s}' % match_group_key, '@@UNRESOLVABLE KEY >%s<@@' %(key.name))
                    else:
                        key_nesting.append(match_group_key)                        
                        possible_abort("Key %s cant be resolved: %s not found (%s)" %(key.name, match_group_key,'->'.join(key_nesting)), fail_on_error)                    
            return done

        def handle_python_function(key, done):
            """
            handle (python) functions $()
            """
            functions = re.findall(self.FUNCTION_IDENTIFIER_RE, str(key.value))
            done = done and len(functions) == 0
            for match_group_function in functions:
                try:                    
                    value = eval(match_group_function, {"__builtins__": None}, self.safe_dict)
                    if value != None:
                        key.value = key.value.replace('$(%s)' % match_group_function, str(value))                            
                except Exception as e:                                        
                    possible_abort("Inline python >%s< cant be evaluated: %s" %(match_group_function, e), fail_on_error)                    
                    key.value = match_group_function
            return done

        def handle_external_script(key, done):
            """
            handle external scripts $[ref: ]
            """
            functions = re.findall(self.SCRIPT_IDENTIFIER_RE, str(key.value))
            done = done and len(functions) == 0
            for match_group_function in functions:
                try:
                    ref = match_group_function[0]                    
                    parms = match_group_function[1]    
                    command_string = self.script_dict.get(ref)         
                    if command_string:                    
                        start = datetime.now()
                        LOGGER.debug('Script %s exec >%s<' %(ref, command_string + " ".join([parms])))
                        result = run(command_string.split(' ') + [parms], capture_output=True, timeout=5000, shell=False, stdin=PIPE)                    
                        LOGGER.debug('Script %s took %sms' %(ref, datetime.now() - start))
                        if result.stdout != None:
                            key.value = key.value.replace('$[%s:%s]' % (ref, parms), result.stdout.decode('utf8'))                            
                        # TODO: why curl gets a RC 3 here even if its works?
                        if result.returncode > 3:
                            LOGGER.warning('Script %s abended with %s (stdout: %s, stderr: %s)' %(ref, result.returncode, result.stdout, result.stderr))
                            possible_abort("Script %s aborted in key %s" %(ref, result.returncode), fail_on_error)
                    else:                        
                        raise Exception("Function %s, used in key >%s< (%s) not found" %(ref, key.name, key.value))
                except Exception as e:
                    possible_abort("Function %s, used in key >%s< (%s) not found" %(ref, key.name, key.value), fail_on_error)                    
                    key.value = key.value.replace('$[%s: %s]' % (ref, parms), '@@UNRESOLVEABLE FUNCTION %s @@' %ref)                                                                    
            return done

        def clean_value(val):
            # clean escaped values
            if level == 0:
                if isinstance(key.value, str):
                    key.value = key.value.replace('\\${','${')
            LOGGER.debug('%s>>> %s finally => %s' %(level, key.name, key.value))
            # try to convert to son
            try:
                return json.loads(key.value)
            except Exception:
                return key.value

        try:
            if key == None:
                return None
            # check if we got a none-existing key referenced
            val = key.value
            # check for keys and resolve them
            if key.substitute:                
                done = False
                while not done:                    
                    done = handle_string(key, done)                        
                    # check for functions and resolve them
                    done = handle_python_function(key, done)                        
                    # check for external script calls
                    done = handle_external_script(key, done)                        
            # remove escape chars - but only on the very outer level                
            return clean_value(val)
        except Exception as e:
            if fail_on_error:                
                raise e
            else:
                pass

    def resolve_keys(self, keys=[], fail_on_error=True):
        return_value = {}
        if len(keys) == 0:
            keys = self.key_set.keys()
        for key in keys:
            key = self.key_set[key]
            return_value[key.name] = self.resolve(key, fail_on_error=fail_on_error).value
        return return_value

    def resolve_meta(self, keys=[], fail_on_error=True):
        return_value = {}
        if len(keys) == 0:
            keys = self.key_set.keys()
        for key in keys:           
            key = self.key_set[key] 
            return_value[key.name] = key.origin
        return return_value

    def resolve(self, key, fail_on_error=True):
        """
        Resolve single key        
        """        
        #depending if we got a keyname or just a string to resolve we get the value of the string
        if isinstance(key, str):
            key = ConfigValue('_dummy', key)                    
        key.value = self._resolve_key(key, fail_on_error=fail_on_error)        
        return key

    def __init__(self, key_set, config={}):        
        self.key_set = key_set
        self.config = config

        #add any needed builtins back in.            
        for key in self.config.get('functions'):
            try:                                
                self.safe_dict[key] = getattr(__builtins__, key)
            except Exception as e:                
                try:
                    self.safe_dict[key] = __builtins__.get(key)
                except Exception as e:
                    LOGGER.warning('Cant find function %s in builtins' %key)
        #build a list of external script modules             
        self.script_dict = self.config.get('scripts', {})            

if __name__== "__main__":       
    parser = argparse.ArgumentParser()
    parser.add_argument('-p','--path', nargs='+', action='append', help='<Required> lookup path', required=True)
    parser.add_argument('-c','--config', action='store', help='<Optional> configuration', required=False)    
    parser.add_argument('-o', '--outputfile', action='store', help='<Optional> output file', required=False)    
    parser.add_argument('-i', '--inputfile', action='store', help='<Optional> file with yaml list of variables to resolve', required=False)    
    parser.add_argument('--outputformat', action='store', help='<Optional> output format (json or yaml)', default='yaml', required=False)    
    parser.add_argument('--origins', action='store_true', help='<Optional> show value origin instead of resolved value', required=False)    
    parser.add_argument('--ignoreerrors', action='store_true', default=False, help='Continue on errors, will set @@ eyecatcher for errors', required=False)        
    args = parser.parse_args()
    global_config_file = args.config
    if not global_config_file:
        global_config_file = os.environ.get('CONFIG', './config.yaml')

    if os.path.exists(global_config_file):
        try:
            with open(global_config_file, 'rb') as file:
                LOGGER.info('Reading global config from %s' %global_config_file)
                ConfigResolver.global_config = yaml.safe_load(file.read())                             
        except Exception as e:
            possible_abort('File %s could not be read: %s' %(args.inputfile, e), True)

    if not ConfigResolver.global_config.get('loglevel'):
        ConfigResolver.global_config['loglevel'] = logging.WARN
    LOGGER.setLevel(ConfigResolver.global_config['loglevel'])

    # None will resolve all the keys
    keys_to_resolve = []
    if args.inputfile:
        try:
            with open(args.inputfile, 'rb') as file:
                LOGGER.info('Reading keys to resolve from from %s' %args.inputfile)
                keys_to_resolve = yaml.safe_load(file.read())                             
        except Exception as e:
            possible_abort('File %s could not be read: %s' %(args.inputfile, e), True)
    
    # do this on every folder specified and merge    
    keys = ConfigReader(args.path, config=ConfigResolver.global_config).values    
    if args.origins:   
        origins = ConfigResolver(keys, config=ConfigResolver.global_config).resolve_meta(keys=keys_to_resolve, fail_on_error=False)
        print(handle_outputformat(args, origins))
    else:        
        keyvals = ConfigResolver(keys, config=ConfigResolver.global_config).resolve_keys(keys=keys_to_resolve, fail_on_error=not args.ignoreerrors)
        output = handle_outputformat(args, keyvals)
        
        # care about output
        if args.outputfile:
            with open(args.outputfile, 'w+', encoding='utf-8') as outputfile:
                outputfile.write(output)
        else:
            print(output)    
