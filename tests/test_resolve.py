import unittest
import os
import json
from rc import ConfigValue, ConfigResolver, ConfigReader
 
class StringResolverTest(unittest.TestCase):

    def setUp(self):
        self.keys = ConfigReader(os.path.join(os.path.dirname(__file__)),).values                        
        print('KEYS %s' %self.keys)
        self.resolver = ConfigResolver(self.keys)

    def test_instantiate_good(self):                        
       resolver = ConfigResolver([])        
       self.assertEquals(True, isinstance(resolver, ConfigResolver))

    def test_instantiate_bad(self):
       try:
           resolver = ConfigResolver(None)
       except Exception as e:
           self.assertTrue(e == None)

    def test_static_string(self):                
        self.resolver.resolve('static_string_key')

    def test_string_reference_1(self):                
        meta = self.resolver.resolve('${string_key_reference_1}')                        
        self.assertTrue(meta != None)
        self.assertTrue(isinstance(meta, ConfigValue))        
        self.assertEquals('STRING KEY REFERENCING STATIC STRING VALUE', meta.value)

class ExternalFunctionResolverTest(unittest.TestCase):
    
    def setUp(self):
        self.keys = ConfigReader(os.path.join(os.path.dirname(__file__)),).values                        
        print('KEYS %s' %self.keys)
        self.resolver = ConfigResolver(self.keys)

    def test_instantiate_good(self):                        
       resolver = ConfigResolver([])        
       self.assertEquals(True, isinstance(resolver, ConfigResolver))

    def test_instantiate_bad(self):
       try:
           resolver = ConfigResolver(None)
       except Exception as e:
           self.assertTrue(e == None)

    def test_static_string(self):                
        self.resolver.resolve('static_string_key')