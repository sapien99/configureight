# Configur8
[![Build Status](https://travis-ci.org/joemccann/dillinger.svg?branch=master)](https://travis-ci.org/sapien99/configur8)

Configur8 (Configurate) is a tool for generating configuration using overlays and nested variables. Its mainly thought to be used with creating helms values.yaml but can be use in various ways.

## Tech
Configur8 is written in python3.6 and is dependent on pyyaml for yaml parsing. Releases for windows and linux (created with pyinstaller) will provide RTR binaries for linux, mac and windows without installing anything

## Installation
### python installation
Fetch python3.6+ and do the usual
```sh
pip install -r requirements.txt
```
### binary installation
Just copy the file to your path. Using configur8 you will specify multiple folders as input. .yaml and .json files in those folders will form the base and overlays of your variables. 

## Principles and Thoughts
### General
Configur8 uses a 2 step aproach to create the final values. The first phase will take care that variables are overridden in the right order, in the second phase the variables will be resolved, taking care of nested keys.
```sh
con8 -p base -p envdev -p subenvdev
```
This example will take all the variables of base and extend/override with the variables from envdev. The result will be extended/overridden with the values of subenvdev - so multiple layers arent just supported but suggested.
### Nested keys
Nested Keys give you the possibility to separate rules from variables or parts of variables . What does that mean and what can it be used for? A simple example is a mongodb connection url. Image you have a set of mongodbs, all on the same server but with different credentials and database names. The pattern looks like this
```sh
mongo://${mongouser}:${mongopassword}@${mongohost}/${mongodb}
```
Quite some variables, right? Of course this can be done in just one key, hardcoding everything in a file for production and one for the dev environment. But wouldnt it be better to keep the pattern and the values separate? mongouser, -password and db seem to be dependent on the application and the environment while just mongohost depends on the environment.

A logical structure like this
```sh
base
  envdev
    envdevapp1
      application1
    envdevapp1
      application2
```
would help in this case. envdev defines the environment parameter mongohost, while envdevapp1 and envdevapp2 define "mixed" variables (the relation between environment and application), like the users and passwords for application1 and application2 within the dev environment. application1 and application2 contain "pure" application specific values - like the pattern of the connectionstring or other application specific values or patterns.

Sounds overcomplex? On the first thought for sure. On second thought its way more flexible than keeping all the environment specific values for application1 in one file or all the values of both applications in the envdev file. Additionally to this you maybe want to group certain variables in separate files for better observability.

Lets take the mentioned structure as a sample, having the following structure. Its looks a bit different, right? The reason for this is to split responsibilities. For an instance environments/envdev could come from a git repository the developers have access to while environments/envprod possibly could come from a git repository only the operation guys have access to.

```sh
base
  base_vars.yaml
  base_vars2.json
envs
  dev
    dev_vars.yaml
  devapp1
    app1_on_dev_vars.yaml
  devapp2
    app1_on_dev_vars.yaml
  prod
    prod_vars.yaml
  prodapp1
    app1_on_prod_vars.yaml
apps
  app1
    app1_vars.yaml
  app2
    app2_vars.yaml
```
### Inline python
Additional to static keys you can use python functions to further enhance your keys. This is quite handy when it comes to calculating port offsets, converting something to upper/lowercase etc.
```sh
port.with.offset=$(5+${offset})
```
or something like this
```sh
uppercase_something=$(${lowervasevalue}.upper())
conversion_to_int=$(int(${eight}))
```
In principle the python builtins are supported, but you can granularly configure the allowed functions using the configur8 config file. 
### External script input
You can pretty easy extend functionality with calling external scripts, fetching data from a webservice, doing some calculations or other stuff that its more difficult than just calling inline python. This example shows how to populate a config key with your external ip - using the api.ipify.org service.

External scripts are defined in the config and are referenced using an alias. They will take arguments as you specify them, separated by blank. If you dont want the script to use any arguments (like when doing a curl on ipify) just use the reference and pass nothing
```sh
externalIp=$[ipify:]
echoedString=$[echo:somestring ${externalIp}]
```
### Defining Configuration Keys
Configuration keys can be defined either in json or in yaml - whatever you prefer. You can use the "object-notation" like notation where each variable file contains an array of config key definitions. Beside the key name and its value there is also an optional meta-variable: substituted. Its quite handy when you have sequences like ${}, $(), $[] which are used as eyecatchers by configur8. You can either escape them in the values using a backslash \${} or you can disable the substitution of this key as a whole.

```yaml
- key: "someKey"    
  value: "some value"
- key: "someOtherKey"    
  value: "some other ${value}",
  substitute: false
```
or in json
```javascript
[
 {
  "key": "someKey",
  "value": "some value"
 },
 {
  "key": "someOtherKey",
  "value": "some other value",
  "substitute": false
 }
]
```
If this seems to be too complex you can use the dict-notation - which is a bit less to write. Metavars can also be used by defining a meta-var (which wont appear in the output) with a special suffix.
```yaml
someKey:"some value"
someOtherKey: "some other ${value}"
someOtherKey._substitute: false
```
or
```javascript
{
  "someKey":"some value",
  "someOtherKey": "some other ${value}",
  "someOtherKey._substitute": false
}
```
### Configuration
The configuration file controls which python inline functions are allowed, the references to external scripts and things like the current loglevel or if stacktraces should be displayed in error cases. It can be specified using the -c or --configuration option or will implicitly be searched as a con8.yaml in the working directory. If no configuration is found the default values will be used 
```bash
# custom script aliases, references by $[echo: xxx]. Default: no scripts
scripts:
  echo: "echo -n ECHOED"  
  ipify: "curl --silent https://api.ipify.org"  
# allowed python inline functions. Default: all buildin but import
functions:
  - int  
# loglevel. Default ERROR with no stacks printed
loglevel: DEBUG
stacks: true
```

## Usage
Lets take the structure from the previous chapter as a sample. This will print the values in yaml format to stdout
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 
```
### Outputfile
you can also specify a dedicated output file using the -o or --output argument
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 -o values.yaml
```
### Inputfile
the inputfile option is quite handy when you dont want to have ALL the keys in the output. Passing a yaml file as input containing a list of keys to resolve will result in just these keys to be resolved. Keys references by those will also be resolved of course, but wont appear in the output
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 -i demo/keylist.yaml -o values.yaml

{
  "echoedString": "ECHOED somestring envdev"
}
```
### IgnoreErrors
If you really want to resolve even in case of an error (an undefined function, a mistyped and therefore not found key etc.) use the --ignoreerrors argument. This makes just sense in edge cases but you should avoid it
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 --ignoreerrors
```
### Output Format
One can specify the output format (either yaml or json) using the --outputformat parameter. Default is yaml
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 --outputformat json
```
### Origin
The overlays etc. may become quite complex in a bigger real world example. The --origin argument should help there. Using this argument prints the origin files the keys were taken from instead of the keys values.
```sh
con8 -p base -p envs/dev -p envs/devapp1 -p apps/app1 --origin

"basevar1": "tests/base/base_vars.yaml",
"basevar2": "tests/base/base_vars.yaml",
"echoedString": "tests/apps/app1/app1_vars.yaml",
"env.name": "tests/envs/dev/dev_vars.yaml",
"integerEight": "tests/apps/app1/app1_vars.yaml",
"nosubstitutationKeyFromDict": "tests/apps/app1/app1_vars_dict.yaml",
"offset": "tests/envs/dev/dev_vars.yaml",
"port": "tests/apps/app1/app1_vars.yaml",
"stringEight": "tests/base/base_vars.yaml",
"stringKeyFromDict": "tests/apps/app1/app1_vars_dict.yaml",
"upperCaseEnvname": "tests/apps/app1/app1_vars.yaml"
```

