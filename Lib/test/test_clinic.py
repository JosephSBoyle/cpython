# Argument Clinic
# Copyright 2012-2013 by Larry Hastings.
# Licensed to the PSF under a contributor agreement.

from test import support, test_tools
from test.support import os_helper
from textwrap import dedent
from unittest import TestCase
import collections
import inspect
import os.path
import sys
import unittest

test_tools.skip_if_missing('clinic')
with test_tools.imports_under_tool('clinic'):
    import clinic
    from clinic import DSLParser


class FakeConverter:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class FakeConverterFactory:
    def __init__(self, name):
        self.name = name

    def __call__(self, name, default, **kwargs):
        return FakeConverter(self.name, kwargs)


class FakeConvertersDict:
    def __init__(self):
        self.used_converters = {}

    def get(self, name, default):
        return self.used_converters.setdefault(name, FakeConverterFactory(name))

c = clinic.Clinic(language='C', filename = "file")

class FakeClinic:
    def __init__(self):
        self.converters = FakeConvertersDict()
        self.legacy_converters = FakeConvertersDict()
        self.language = clinic.CLanguage(None)
        self.filename = None
        self.destination_buffers = {}
        self.block_parser = clinic.BlockParser('', self.language)
        self.modules = collections.OrderedDict()
        self.classes = collections.OrderedDict()
        clinic.clinic = self
        self.name = "FakeClinic"
        self.line_prefix = self.line_suffix = ''
        self.destinations = {}
        self.add_destination("block", "buffer")
        self.add_destination("file", "buffer")
        self.add_destination("suppress", "suppress")
        d = self.destinations.get
        self.field_destinations = collections.OrderedDict((
            ('docstring_prototype', d('suppress')),
            ('docstring_definition', d('block')),
            ('methoddef_define', d('block')),
            ('impl_prototype', d('block')),
            ('parser_prototype', d('suppress')),
            ('parser_definition', d('block')),
            ('impl_definition', d('block')),
        ))

    def get_destination(self, name):
        d = self.destinations.get(name)
        if not d:
            sys.exit("Destination does not exist: " + repr(name))
        return d

    def add_destination(self, name, type, *args):
        if name in self.destinations:
            sys.exit("Destination already exists: " + repr(name))
        self.destinations[name] = clinic.Destination(name, type, self, *args)

    def is_directive(self, name):
        return name == "module"

    def directive(self, name, args):
        self.called_directives[name] = args

    _module_and_class = clinic.Clinic._module_and_class

class ClinicWholeFileTest(TestCase):
    def test_eol(self):
        # regression test:
        # clinic's block parser didn't recognize
        # the "end line" for the block if it
        # didn't end in "\n" (as in, the last)
        # byte of the file was '/'.
        # so it would spit out an end line for you.
        # and since you really already had one,
        # the last line of the block got corrupted.
        c = clinic.Clinic(clinic.CLanguage(None), filename="file")
        raw = "/*[clinic]\nfoo\n[clinic]*/"
        cooked, _ = c.parse(raw)
        lines = cooked.splitlines()
        end_line = lines[2].rstrip()
        # this test is redundant, it's just here explicitly to catch
        # the regression test so we don't forget what it looked like
        self.assertNotEqual(end_line, "[clinic]*/[clinic]*/")
        self.assertEqual(end_line, "[clinic]*/")



class ClinicGroupPermuterTest(TestCase):
    def _test(self, l, m, r, output):
        computed = clinic.permute_optional_groups(l, m, r)
        self.assertEqual(output, computed)

    def test_range(self):
        self._test([['start']], ['stop'], [['step']],
          (
            ('stop',),
            ('start', 'stop',),
            ('start', 'stop', 'step',),
          ))

    def test_add_window(self):
        self._test([['x', 'y']], ['ch'], [['attr']],
          (
            ('ch',),
            ('ch', 'attr'),
            ('x', 'y', 'ch',),
            ('x', 'y', 'ch', 'attr'),
          ))

    def test_ludicrous(self):
        self._test([['a1', 'a2', 'a3'], ['b1', 'b2']], ['c1'], [['d1', 'd2'], ['e1', 'e2', 'e3']],
          (
          ('c1',),
          ('b1', 'b2', 'c1'),
          ('b1', 'b2', 'c1', 'd1', 'd2'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1', 'd1', 'd2'),
          ('a1', 'a2', 'a3', 'b1', 'b2', 'c1', 'd1', 'd2', 'e1', 'e2', 'e3'),
          ))

    def test_right_only(self):
        self._test([], [], [['a'],['b'],['c']],
          (
          (),
          ('a',),
          ('a', 'b'),
          ('a', 'b', 'c')
          ))

    def test_have_left_options_but_required_is_empty(self):
        def fn():
            clinic.permute_optional_groups(['a'], [], [])
        self.assertRaises(ValueError, fn)


class ClinicLinearFormatTest(TestCase):
    def _test(self, input, output, **kwargs):
        computed = clinic.linear_format(input, **kwargs)
        self.assertEqual(output, computed)

    def test_empty_strings(self):
        self._test('', '')

    def test_solo_newline(self):
        self._test('\n', '\n')

    def test_no_substitution(self):
        self._test("""
          abc
        """, """
          abc
        """)

    def test_empty_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          def
        """, name='')

    def test_single_line_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          GARGLE
          def
        """, name='GARGLE')

    def test_multiline_substitution(self):
        self._test("""
          abc
          {name}
          def
        """, """
          abc
          bingle
          bungle

          def
        """, name='bingle\nbungle\n')

class InertParser:
    def __init__(self, clinic):
        pass

    def parse(self, block):
        pass

class CopyParser:
    def __init__(self, clinic):
        pass

    def parse(self, block):
        block.output = block.input


class ClinicBlockParserTest(TestCase):
    def _test(self, input, output):
        language = clinic.CLanguage(None)

        blocks = list(clinic.BlockParser(input, language))
        writer = clinic.BlockPrinter(language)
        for block in blocks:
            writer.print_block(block)
        output = writer.f.getvalue()
        assert output == input, "output != input!\n\noutput " + repr(output) + "\n\n input " + repr(input)

    def round_trip(self, input):
        return self._test(input, input)

    def test_round_trip_1(self):
        self.round_trip("""
            verbatim text here
            lah dee dah
        """)
    def test_round_trip_2(self):
        self.round_trip("""
    verbatim text here
    lah dee dah
/*[inert]
abc
[inert]*/
def
/*[inert checksum: 7b18d017f89f61cf17d47f92749ea6930a3f1deb]*/
xyz
""")

    def _test_clinic(self, input, output):
        language = clinic.CLanguage(None)
        c = clinic.Clinic(language, filename="file")
        c.parsers['inert'] = InertParser(c)
        c.parsers['copy'] = CopyParser(c)
        computed, _ = c.parse(input)
        self.assertEqual(output, computed)

    def test_clinic_1(self):
        self._test_clinic("""
    verbatim text here
    lah dee dah
/*[copy input]
def
[copy start generated code]*/
abc
/*[copy end generated code: output=03cfd743661f0797 input=7b18d017f89f61cf]*/
xyz
""", """
    verbatim text here
    lah dee dah
/*[copy input]
def
[copy start generated code]*/
def
/*[copy end generated code: output=7b18d017f89f61cf input=7b18d017f89f61cf]*/
xyz
""")


class ClinicParserTest(TestCase):
    def checkDocstring(self, fn, expected):
        self.assertTrue(hasattr(fn, "docstring"))
        self.assertEqual(fn.docstring.strip(),
                         dedent(expected).strip())

    def test_trivial(self):
        parser = DSLParser(FakeClinic())
        block = clinic.Block("""
            module os
            os.access
        """)
        parser.parse(block)
        module, function = block.signatures
        self.assertEqual("access", function.name)
        self.assertEqual("os", module.name)

    def test_ignore_line(self):
        block = self.parse(dedent("""
            #
            module os
            os.access
        """))
        module, function = block.signatures
        self.assertEqual("access", function.name)
        self.assertEqual("os", module.name)

    def test_param(self):
        function = self.parse_function("""
            module os
            os.access
                path: int
        """)
        self.assertEqual("access", function.name)
        self.assertEqual(2, len(function.parameters))
        p = function.parameters['path']
        self.assertEqual('path', p.name)
        self.assertIsInstance(p.converter, clinic.int_converter)

    def test_param_default(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: bool = True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(True, p.default)

    def test_param_with_continuations(self):
        function = self.parse_function(r"""
            module os
            os.access
                follow_symlinks: \
                bool \
                = \
                True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(True, p.default)

    def test_param_default_expression(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: int(c_default='MAXSIZE') = sys.maxsize
            """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(sys.maxsize, p.default)
        self.assertEqual("MAXSIZE", p.converter.c_default)

        expected_msg = (
            "Error on line 0:\n"
            "When you specify a named constant ('sys.maxsize') as your default value,\n"
            "you MUST specify a valid c_default.\n"
        )
        out = self.parse_function_should_fail("""
            module os
            os.access
                follow_symlinks: int = sys.maxsize
        """)
        self.assertEqual(out, expected_msg)

    def test_param_no_docstring(self):
        function = self.parse_function("""
            module os
            os.access
                follow_symlinks: bool = True
                something_else: str = ''
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(3, len(function.parameters))
        conv = function.parameters['something_else'].converter
        self.assertIsInstance(conv, clinic.str_converter)

    def test_param_default_parameters_out_of_order(self):
        expected_msg = (
            "Error on line 0:\n"
            "Can't have a parameter without a default ('something_else')\n"
            "after a parameter with a default!\n"
        )
        out = self.parse_function_should_fail("""
            module os
            os.access
                follow_symlinks: bool = True
                something_else: str""")
        self.assertEqual(out, expected_msg)

    def disabled_test_converter_arguments(self):
        function = self.parse_function("""
            module os
            os.access
                path: path_t(allow_fd=1)
        """)
        p = function.parameters['path']
        self.assertEqual(1, p.converter.args['allow_fd'])

    def test_function_docstring(self):
        function = self.parse_function("""
            module os
            os.stat as os_stat_fn

               path: str
                   Path to be examined

            Perform a stat system call on the given path.
        """)
        self.checkDocstring(function, """
            stat($module, /, path)
            --

            Perform a stat system call on the given path.

              path
                Path to be examined
        """)

    def test_explicit_parameters_in_docstring(self):
        function = self.parse_function(dedent("""
            module foo
            foo.bar
              x: int
                 Documentation for x.
              y: int

            This is the documentation for foo.

            Okay, we're done here.
        """))
        self.checkDocstring(function, """
            bar($module, /, x, y)
            --

            This is the documentation for foo.

              x
                Documentation for x.

            Okay, we're done here.
        """)

    def test_parser_regression_special_character_in_parameter_column_of_docstring_first_line(self):
        function = self.parse_function(dedent("""
            module os
            os.stat
                path: str
            This/used to break Clinic!
        """))
        self.checkDocstring(function, """
            stat($module, /, path)
            --

            This/used to break Clinic!
        """)

    def test_c_name(self):
        function = self.parse_function("""
            module os
            os.stat as os_stat_fn
        """)
        self.assertEqual("os_stat_fn", function.c_basename)

    def test_return_converter(self):
        function = self.parse_function("""
            module os
            os.stat -> int
        """)
        self.assertIsInstance(function.return_converter, clinic.int_return_converter)

    def test_star(self):
        function = self.parse_function("""
            module os
            os.access
                *
                follow_symlinks: bool = True
        """)
        p = function.parameters['follow_symlinks']
        self.assertEqual(inspect.Parameter.KEYWORD_ONLY, p.kind)
        self.assertEqual(0, p.group)

    def test_group(self):
        function = self.parse_function("""
            module window
            window.border
                [
                ls: int
                ]
                /
        """)
        p = function.parameters['ls']
        self.assertEqual(1, p.group)

    def test_left_group(self):
        function = self.parse_function("""
            module curses
            curses.addch
                [
                y: int
                    Y-coordinate.
                x: int
                    X-coordinate.
                ]
                ch: char
                    Character to add.
                [
                attr: long
                    Attributes for the character.
                ]
                /
        """)
        dataset = (
            ('y', -1), ('x', -1),
            ('ch', 0),
            ('attr', 1),
        )
        for name, group in dataset:
            with self.subTest(name=name, group=group):
                p = function.parameters[name]
                self.assertEqual(p.group, group)
                self.assertEqual(p.kind, inspect.Parameter.POSITIONAL_ONLY)
        self.checkDocstring(function, """
            addch([y, x,] ch, [attr])


              y
                Y-coordinate.
              x
                X-coordinate.
              ch
                Character to add.
              attr
                Attributes for the character.
        """)

    def test_nested_groups(self):
        function = self.parse_function("""
            module curses
            curses.imaginary
               [
               [
               y1: int
                 Y-coordinate.
               y2: int
                 Y-coordinate.
               ]
               x1: int
                 X-coordinate.
               x2: int
                 X-coordinate.
               ]
               ch: char
                 Character to add.
               [
               attr1: long
                 Attributes for the character.
               attr2: long
                 Attributes for the character.
               attr3: long
                 Attributes for the character.
               [
               attr4: long
                 Attributes for the character.
               attr5: long
                 Attributes for the character.
               attr6: long
                 Attributes for the character.
               ]
               ]
               /
        """)
        dataset = (
            ('y1', -2), ('y2', -2),
            ('x1', -1), ('x2', -1),
            ('ch', 0),
            ('attr1', 1), ('attr2', 1), ('attr3', 1),
            ('attr4', 2), ('attr5', 2), ('attr6', 2),
        )
        for name, group in dataset:
            with self.subTest(name=name, group=group):
                p = function.parameters[name]
                self.assertEqual(p.group, group)
                self.assertEqual(p.kind, inspect.Parameter.POSITIONAL_ONLY)

        self.checkDocstring(function, """
            imaginary([[y1, y2,] x1, x2,] ch, [attr1, attr2, attr3, [attr4, attr5,
                      attr6]])


              y1
                Y-coordinate.
              y2
                Y-coordinate.
              x1
                X-coordinate.
              x2
                X-coordinate.
              ch
                Character to add.
              attr1
                Attributes for the character.
              attr2
                Attributes for the character.
              attr3
                Attributes for the character.
              attr4
                Attributes for the character.
              attr5
                Attributes for the character.
              attr6
                Attributes for the character.
        """)

    def parse_function_should_fail(self, s):
        with support.captured_stdout() as stdout:
            with self.assertRaises(SystemExit):
                self.parse_function(s)
        return stdout.getvalue()

    def test_disallowed_grouping__two_top_groups_on_left(self):
        expected_msg = (
            'Error on line 0:\n'
            'Function two_top_groups_on_left has an unsupported group '
            'configuration. (Unexpected state 2.b)\n'
        )
        out = self.parse_function_should_fail("""
            module foo
            foo.two_top_groups_on_left
                [
                group1 : int
                ]
                [
                group2 : int
                ]
                param: int
        """)
        self.assertEqual(out, expected_msg)

    def test_disallowed_grouping__two_top_groups_on_right(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.two_top_groups_on_right
                param: int
                [
                group1 : int
                ]
                [
                group2 : int
                ]
        """)
        msg = (
            "Function two_top_groups_on_right has an unsupported group "
            "configuration. (Unexpected state 6.b)"
        )
        self.assertIn(msg, out)

    def test_disallowed_grouping__parameter_after_group_on_right(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.parameter_after_group_on_right
                param: int
                [
                [
                group1 : int
                ]
                group2 : int
                ]
        """)
        msg = (
            "Function parameter_after_group_on_right has an unsupported group "
            "configuration. (Unexpected state 6.a)"
        )
        self.assertIn(msg, out)

    def test_disallowed_grouping__group_after_parameter_on_left(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.group_after_parameter_on_left
                [
                group2 : int
                [
                group1 : int
                ]
                ]
                param: int
        """)
        msg = (
            "Function group_after_parameter_on_left has an unsupported group "
            "configuration. (Unexpected state 2.b)"
        )
        self.assertIn(msg, out)

    def test_disallowed_grouping__empty_group_on_left(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.empty_group
                [
                [
                ]
                group2 : int
                ]
                param: int
        """)
        msg = (
            "Function empty_group has an empty group.\n"
            "All groups must contain at least one parameter."
        )
        self.assertIn(msg, out)

    def test_disallowed_grouping__empty_group_on_right(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.empty_group
                param: int
                [
                [
                ]
                group2 : int
                ]
        """)
        msg = (
            "Function empty_group has an empty group.\n"
            "All groups must contain at least one parameter."
        )
        self.assertIn(msg, out)

    def test_disallowed_grouping__no_matching_bracket(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.empty_group
                param: int
                ]
                group2: int
                ]
        """)
        msg = "Function empty_group has a ] without a matching [."
        self.assertIn(msg, out)

    def test_no_parameters(self):
        function = self.parse_function("""
            module foo
            foo.bar

            Docstring

        """)
        self.assertEqual("bar($module, /)\n--\n\nDocstring", function.docstring)
        self.assertEqual(1, len(function.parameters)) # self!

    def test_init_with_no_parameters(self):
        function = self.parse_function("""
            module foo
            class foo.Bar "unused" "notneeded"
            foo.Bar.__init__

            Docstring

        """, signatures_in_block=3, function_index=2)

        # self is not in the signature
        self.assertEqual("Bar()\n--\n\nDocstring", function.docstring)
        # but it *is* a parameter
        self.assertEqual(1, len(function.parameters))

    def test_illegal_module_line(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar => int
                /
        """)
        msg = "Illegal function name: foo.bar => int"
        self.assertIn(msg, out)

    def test_illegal_c_basename(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar as 935
                /
        """)
        msg = "Illegal C basename: 935"
        self.assertIn(msg, out)

    def test_single_star(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
                *
                *
        """)
        self.assertIn("Function bar uses '*' more than once.", out)

    def test_parameters_required_after_star(self):
        dataset = (
            "module foo\nfoo.bar\n  *",
            "module foo\nfoo.bar\n  *\nDocstring here.",
            "module foo\nfoo.bar\n  this: int\n  *",
            "module foo\nfoo.bar\n  this: int\n  *\nDocstring.",
        )
        msg = "Function bar specifies '*' without any parameters afterwards."
        for block in dataset:
            with self.subTest(block=block):
                out = self.parse_function_should_fail(block)
                self.assertIn(msg, out)

    def test_single_slash(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
                /
                /
        """)
        msg = (
            "Function bar has an unsupported group configuration. "
            "(Unexpected state 0.d)"
        )
        self.assertIn(msg, out)

    def test_double_slash(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
                a: int
                /
                b: int
                /
        """)
        msg = "Function bar uses '/' more than once."
        self.assertIn(msg, out)

    def test_mix_star_and_slash(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
               x: int
               y: int
               *
               z: int
               /
        """)
        msg = (
            "Function bar mixes keyword-only and positional-only parameters, "
            "which is unsupported."
        )
        self.assertIn(msg, out)

    def test_parameters_not_permitted_after_slash_for_now(self):
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
                /
                x: int
        """)
        msg = (
            "Function bar has an unsupported group configuration. "
            "(Unexpected state 0.d)"
        )
        self.assertIn(msg, out)

    def test_parameters_no_more_than_one_vararg(self):
        expected_msg = (
            "Error on line 0:\n"
            "Too many var args\n"
        )
        out = self.parse_function_should_fail("""
            module foo
            foo.bar
               *vararg1: object
               *vararg2: object
        """)
        self.assertEqual(out, expected_msg)

    def test_function_not_at_column_0(self):
        function = self.parse_function("""
              module foo
              foo.bar
                x: int
                  Nested docstring here, goeth.
                *
                y: str
              Not at column 0!
        """)
        self.checkDocstring(function, """
            bar($module, /, x, *, y)
            --

            Not at column 0!

              x
                Nested docstring here, goeth.
        """)

    def test_directive(self):
        c = FakeClinic()
        parser = DSLParser(c)
        parser.flag = False
        parser.directives['setflag'] = lambda : setattr(parser, 'flag', True)
        block = clinic.Block("setflag")
        parser.parse(block)
        self.assertTrue(parser.flag)

    def test_legacy_converters(self):
        block = self.parse('module os\nos.access\n   path: "s"')
        module, function = block.signatures
        conv = (function.parameters['path']).converter
        self.assertIsInstance(conv, clinic.str_converter)

    def test_legacy_converters_non_string_constant_annotation(self):
        expected_failure_message = (
            "Error on line 0:\n"
            "Annotations must be either a name, a function call, or a string.\n"
        )
        dataset = (
            'module os\nos.access\n   path: 42',
            'module os\nos.access\n   path: 42.42',
            'module os\nos.access\n   path: 42j',
            'module os\nos.access\n   path: b"42"',
        )
        for block in dataset:
            with self.subTest(block=block):
                out = self.parse_function_should_fail(block)
                self.assertEqual(out, expected_failure_message)

    def test_other_bizarre_things_in_annotations_fail(self):
        expected_failure_message = (
            "Error on line 0:\n"
            "Annotations must be either a name, a function call, or a string.\n"
        )
        dataset = (
            'module os\nos.access\n   path: {"some": "dictionary"}',
            'module os\nos.access\n   path: ["list", "of", "strings"]',
            'module os\nos.access\n   path: (x for x in range(42))',
        )
        for block in dataset:
            with self.subTest(block=block):
                out = self.parse_function_should_fail(block)
                self.assertEqual(out, expected_failure_message)

    def test_kwarg_splats_disallowed_in_function_call_annotations(self):
        expected_error_msg = (
            "Error on line 0:\n"
            "Cannot use a kwarg splat in a function-call annotation\n"
        )
        dataset = (
            'module fo\nfo.barbaz\n   o: bool(**{None: "bang!"})',
            'module fo\nfo.barbaz -> bool(**{None: "bang!"})',
            'module fo\nfo.barbaz -> bool(**{"bang": 42})',
            'module fo\nfo.barbaz\n   o: bool(**{"bang": None})',
        )
        for fn in dataset:
            with self.subTest(fn=fn):
                out = self.parse_function_should_fail(fn)
                self.assertEqual(out, expected_error_msg)

    def test_self_param_placement(self):
        expected_error_msg = (
            "Error on line 0:\n"
            "A 'self' parameter, if specified, must be the very first thing "
            "in the parameter block.\n"
        )
        block = """
            module foo
            foo.func
                a: int
                self: self(type="PyObject *")
        """
        out = self.parse_function_should_fail(block)
        self.assertEqual(out, expected_error_msg)

    def test_self_param_cannot_be_optional(self):
        expected_error_msg = (
            "Error on line 0:\n"
            "A 'self' parameter cannot be marked optional.\n"
        )
        block = """
            module foo
            foo.func
                self: self(type="PyObject *") = None
        """
        out = self.parse_function_should_fail(block)
        self.assertEqual(out, expected_error_msg)

    def test_defining_class_param_placement(self):
        expected_error_msg = (
            "Error on line 0:\n"
            "A 'defining_class' parameter, if specified, must either be the "
            "first thing in the parameter block, or come just after 'self'.\n"
        )
        block = """
            module foo
            foo.func
                self: self(type="PyObject *")
                a: int
                cls: defining_class
        """
        out = self.parse_function_should_fail(block)
        self.assertEqual(out, expected_error_msg)

    def test_defining_class_param_cannot_be_optional(self):
        expected_error_msg = (
            "Error on line 0:\n"
            "A 'defining_class' parameter cannot be marked optional.\n"
        )
        block = """
            module foo
            foo.func
                cls: defining_class(type="PyObject *") = None
        """
        out = self.parse_function_should_fail(block)
        self.assertEqual(out, expected_error_msg)

    def test_unused_param(self):
        block = self.parse("""
            module foo
            foo.func
                fn: object
                k: float
                i: float(unused=True)
                /
                *
                flag: bool(unused=True) = False
        """)
        sig = block.signatures[1]  # Function index == 1
        params = sig.parameters
        conv = lambda fn: params[fn].converter
        dataset = (
            {"name": "fn", "unused": False},
            {"name": "k", "unused": False},
            {"name": "i", "unused": True},
            {"name": "flag", "unused": True},
        )
        for param in dataset:
            name, unused = param.values()
            with self.subTest(name=name, unused=unused):
                p = conv(name)
                # Verify that the unused flag is parsed correctly.
                self.assertEqual(unused, p.unused)

                # Now, check that we'll produce correct code.
                decl = p.simple_declaration(in_parser=False)
                if unused:
                    self.assertIn("Py_UNUSED", decl)
                else:
                    self.assertNotIn("Py_UNUSED", decl)

                # Make sure the Py_UNUSED macro is not used in the parser body.
                parser_decl = p.simple_declaration(in_parser=True)
                self.assertNotIn("Py_UNUSED", parser_decl)

    def parse(self, text):
        c = FakeClinic()
        parser = DSLParser(c)
        block = clinic.Block(text)
        parser.parse(block)
        return block

    def parse_function(self, text, signatures_in_block=2, function_index=1):
        block = self.parse(text)
        s = block.signatures
        self.assertEqual(len(s), signatures_in_block)
        assert isinstance(s[0], clinic.Module)
        assert isinstance(s[function_index], clinic.Function)
        return s[function_index]

    def test_scaffolding(self):
        # test repr on special values
        self.assertEqual(repr(clinic.unspecified), '<Unspecified>')
        self.assertEqual(repr(clinic.NULL), '<Null>')

        # test that fail fails
        expected = (
            'Error in file "clown.txt" on line 69:\n'
            'The igloos are melting!\n'
        )
        with support.captured_stdout() as stdout:
            with self.assertRaises(SystemExit):
                clinic.fail('The igloos are melting!',
                            filename='clown.txt', line_number=69)
        actual = stdout.getvalue()
        self.assertEqual(actual, expected)


class ClinicExternalTest(TestCase):
    maxDiff = None

    def test_external(self):
        # bpo-42398: Test that the destination file is left unchanged if the
        # content does not change. Moreover, check also that the file
        # modification time does not change in this case.
        source = support.findfile('clinic.test')
        with open(source, 'r', encoding='utf-8') as f:
            orig_contents = f.read()

        with os_helper.temp_dir() as tmp_dir:
            testfile = os.path.join(tmp_dir, 'clinic.test.c')
            with open(testfile, 'w', encoding='utf-8') as f:
                f.write(orig_contents)
            old_mtime_ns = os.stat(testfile).st_mtime_ns

            clinic.parse_file(testfile)

            with open(testfile, 'r', encoding='utf-8') as f:
                new_contents = f.read()
            new_mtime_ns = os.stat(testfile).st_mtime_ns

        self.assertEqual(new_contents, orig_contents)
        # Don't change the file modification time
        # if the content does not change
        self.assertEqual(new_mtime_ns, old_mtime_ns)


try:
    import _testclinic as ac_tester
except ImportError:
    ac_tester = None

@unittest.skipIf(ac_tester is None, "_testclinic is missing")
class ClinicFunctionalTest(unittest.TestCase):
    locals().update((name, getattr(ac_tester, name))
                    for name in dir(ac_tester) if name.startswith('test_'))

    def test_objects_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.objects_converter()
        self.assertEqual(ac_tester.objects_converter(1, 2), (1, 2))
        self.assertEqual(ac_tester.objects_converter([], 'whatever class'), ([], 'whatever class'))
        self.assertEqual(ac_tester.objects_converter(1), (1, None))

    def test_bytes_object_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.bytes_object_converter(1)
        self.assertEqual(ac_tester.bytes_object_converter(b'BytesObject'), (b'BytesObject',))

    def test_byte_array_object_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.byte_array_object_converter(1)
        byte_arr = bytearray(b'ByteArrayObject')
        self.assertEqual(ac_tester.byte_array_object_converter(byte_arr), (byte_arr,))

    def test_unicode_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.unicode_converter(1)
        self.assertEqual(ac_tester.unicode_converter('unicode'), ('unicode',))

    def test_bool_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.bool_converter(False, False, 'not a int')
        self.assertEqual(ac_tester.bool_converter(), (True, True, True))
        self.assertEqual(ac_tester.bool_converter('', [], 5), (False, False, True))
        self.assertEqual(ac_tester.bool_converter(('not empty',), {1: 2}, 0), (True, True, False))

    def test_char_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.char_converter(1)
        with self.assertRaises(TypeError):
            ac_tester.char_converter(b'ab')
        chars = [b'A', b'\a', b'\b', b'\t', b'\n', b'\v', b'\f', b'\r', b'"', b"'", b'?', b'\\', b'\000', b'\377']
        expected = tuple(ord(c) for c in chars)
        self.assertEqual(ac_tester.char_converter(), expected)
        chars = [b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9', b'0', b'a', b'b', b'c', b'd']
        expected = tuple(ord(c) for c in chars)
        self.assertEqual(ac_tester.char_converter(*chars), expected)

    def test_unsigned_char_converter(self):
        from _testcapi import UCHAR_MAX
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(UCHAR_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_char_converter(0, UCHAR_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_char_converter([])
        self.assertEqual(ac_tester.unsigned_char_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_char_converter(0, 0, UCHAR_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_char_converter(0, 0, (UCHAR_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_short_converter(self):
        from _testcapi import SHRT_MIN, SHRT_MAX
        with self.assertRaises(OverflowError):
            ac_tester.short_converter(SHRT_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.short_converter(SHRT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.short_converter([])
        self.assertEqual(ac_tester.short_converter(-1234), (-1234,))
        self.assertEqual(ac_tester.short_converter(4321), (4321,))

    def test_unsigned_short_converter(self):
        from _testcapi import USHRT_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_short_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_short_converter(USHRT_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_short_converter(0, USHRT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_short_converter([])
        self.assertEqual(ac_tester.unsigned_short_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_short_converter(0, 0, USHRT_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_short_converter(0, 0, (USHRT_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_int_converter(self):
        from _testcapi import INT_MIN, INT_MAX
        with self.assertRaises(OverflowError):
            ac_tester.int_converter(INT_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.int_converter(INT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.int_converter(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.int_converter([])
        self.assertEqual(ac_tester.int_converter(), (12, 34, 45))
        self.assertEqual(ac_tester.int_converter(1, 2, '3'), (1, 2, ord('3')))

    def test_unsigned_int_converter(self):
        from _testcapi import UINT_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_int_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_int_converter(UINT_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_int_converter(0, UINT_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_int_converter([])
        self.assertEqual(ac_tester.unsigned_int_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_int_converter(0, 0, UINT_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_int_converter(0, 0, (UINT_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_long_converter(self):
        from _testcapi import LONG_MIN, LONG_MAX
        with self.assertRaises(OverflowError):
            ac_tester.long_converter(LONG_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.long_converter(LONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.long_converter([])
        self.assertEqual(ac_tester.long_converter(), (12,))
        self.assertEqual(ac_tester.long_converter(-1234), (-1234,))

    def test_unsigned_long_converter(self):
        from _testcapi import ULONG_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_long_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_converter(ULONG_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_converter(0, ULONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_long_converter([])
        self.assertEqual(ac_tester.unsigned_long_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_long_converter(0, 0, ULONG_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_long_converter(0, 0, (ULONG_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_long_long_converter(self):
        from _testcapi import LLONG_MIN, LLONG_MAX
        with self.assertRaises(OverflowError):
            ac_tester.long_long_converter(LLONG_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.long_long_converter(LLONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.long_long_converter([])
        self.assertEqual(ac_tester.long_long_converter(), (12,))
        self.assertEqual(ac_tester.long_long_converter(-1234), (-1234,))

    def test_unsigned_long_long_converter(self):
        from _testcapi import ULLONG_MAX
        with self.assertRaises(ValueError):
            ac_tester.unsigned_long_long_converter(-1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_long_converter(ULLONG_MAX + 1)
        with self.assertRaises(OverflowError):
            ac_tester.unsigned_long_long_converter(0, ULLONG_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.unsigned_long_long_converter([])
        self.assertEqual(ac_tester.unsigned_long_long_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.unsigned_long_long_converter(0, 0, ULLONG_MAX + 1), (0, 0, 0))
        self.assertEqual(ac_tester.unsigned_long_long_converter(0, 0, (ULLONG_MAX + 1) * 3 + 123), (0, 0, 123))

    def test_py_ssize_t_converter(self):
        from _testcapi import PY_SSIZE_T_MIN, PY_SSIZE_T_MAX
        with self.assertRaises(OverflowError):
            ac_tester.py_ssize_t_converter(PY_SSIZE_T_MIN - 1)
        with self.assertRaises(OverflowError):
            ac_tester.py_ssize_t_converter(PY_SSIZE_T_MAX + 1)
        with self.assertRaises(TypeError):
            ac_tester.py_ssize_t_converter([])
        self.assertEqual(ac_tester.py_ssize_t_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.py_ssize_t_converter(1, 2, None), (1, 2, 56))

    def test_slice_index_converter(self):
        from _testcapi import PY_SSIZE_T_MIN, PY_SSIZE_T_MAX
        with self.assertRaises(TypeError):
            ac_tester.slice_index_converter([])
        self.assertEqual(ac_tester.slice_index_converter(), (12, 34, 56))
        self.assertEqual(ac_tester.slice_index_converter(1, 2, None), (1, 2, 56))
        self.assertEqual(ac_tester.slice_index_converter(PY_SSIZE_T_MAX, PY_SSIZE_T_MAX + 1, PY_SSIZE_T_MAX + 1234),
                         (PY_SSIZE_T_MAX, PY_SSIZE_T_MAX, PY_SSIZE_T_MAX))
        self.assertEqual(ac_tester.slice_index_converter(PY_SSIZE_T_MIN, PY_SSIZE_T_MIN - 1, PY_SSIZE_T_MIN - 1234),
                         (PY_SSIZE_T_MIN, PY_SSIZE_T_MIN, PY_SSIZE_T_MIN))

    def test_size_t_converter(self):
        with self.assertRaises(ValueError):
            ac_tester.size_t_converter(-1)
        with self.assertRaises(TypeError):
            ac_tester.size_t_converter([])
        self.assertEqual(ac_tester.size_t_converter(), (12,))

    def test_float_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.float_converter([])
        self.assertEqual(ac_tester.float_converter(), (12.5,))
        self.assertEqual(ac_tester.float_converter(-0.5), (-0.5,))

    def test_double_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.double_converter([])
        self.assertEqual(ac_tester.double_converter(), (12.5,))
        self.assertEqual(ac_tester.double_converter(-0.5), (-0.5,))

    def test_py_complex_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.py_complex_converter([])
        self.assertEqual(ac_tester.py_complex_converter(complex(1, 2)), (complex(1, 2),))
        self.assertEqual(ac_tester.py_complex_converter(complex('-1-2j')), (complex('-1-2j'),))
        self.assertEqual(ac_tester.py_complex_converter(-0.5), (-0.5,))
        self.assertEqual(ac_tester.py_complex_converter(10), (10,))

    def test_str_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.str_converter(1)
        with self.assertRaises(TypeError):
            ac_tester.str_converter('a', 'b', 'c')
        with self.assertRaises(ValueError):
            ac_tester.str_converter('a', b'b\0b', 'c')
        self.assertEqual(ac_tester.str_converter('a', b'b', 'c'), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter('a', b'b', b'c'), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter('a', b'b', 'c\0c'), ('a', 'b', 'c\0c'))

    def test_str_converter_encoding(self):
        with self.assertRaises(TypeError):
            ac_tester.str_converter_encoding(1)
        self.assertEqual(ac_tester.str_converter_encoding('a', 'b', 'c'), ('a', 'b', 'c'))
        with self.assertRaises(TypeError):
            ac_tester.str_converter_encoding('a', b'b\0b', 'c')
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', bytearray([ord('c')])), ('a', 'b', 'c'))
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', bytearray([ord('c'), 0, ord('c')])),
                         ('a', 'b', 'c\x00c'))
        self.assertEqual(ac_tester.str_converter_encoding('a', b'b', b'c\x00c'), ('a', 'b', 'c\x00c'))

    def test_py_buffer_converter(self):
        with self.assertRaises(TypeError):
            ac_tester.py_buffer_converter('a', 'b')
        self.assertEqual(ac_tester.py_buffer_converter('abc', bytearray([1, 2, 3])), (b'abc', b'\x01\x02\x03'))

    def test_keywords(self):
        self.assertEqual(ac_tester.keywords(1, 2), (1, 2))
        self.assertEqual(ac_tester.keywords(1, b=2), (1, 2))
        self.assertEqual(ac_tester.keywords(a=1, b=2), (1, 2))

    def test_keywords_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.keywords_kwonly(1, 2)
        self.assertEqual(ac_tester.keywords_kwonly(1, b=2), (1, 2))
        self.assertEqual(ac_tester.keywords_kwonly(a=1, b=2), (1, 2))

    def test_keywords_opt(self):
        self.assertEqual(ac_tester.keywords_opt(1), (1, None, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2, 3), (1, 2, 3))
        self.assertEqual(ac_tester.keywords_opt(1, b=2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_opt(1, 2, c=3), (1, 2, 3))
        self.assertEqual(ac_tester.keywords_opt(a=1, c=3), (1, None, 3))
        self.assertEqual(ac_tester.keywords_opt(a=1, b=2, c=3), (1, 2, 3))

    def test_keywords_opt_kwonly(self):
        self.assertEqual(ac_tester.keywords_opt_kwonly(1), (1, None, None, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.keywords_opt_kwonly(1, 2, 3)
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(a=1, c=3), (1, None, 3, None))
        self.assertEqual(ac_tester.keywords_opt_kwonly(a=1, b=2, c=3, d=4), (1, 2, 3, 4))

    def test_keywords_kwonly_opt(self):
        self.assertEqual(ac_tester.keywords_kwonly_opt(1), (1, None, None))
        with self.assertRaises(TypeError):
            ac_tester.keywords_kwonly_opt(1, 2)
        self.assertEqual(ac_tester.keywords_kwonly_opt(1, b=2), (1, 2, None))
        self.assertEqual(ac_tester.keywords_kwonly_opt(a=1, c=3), (1, None, 3))
        self.assertEqual(ac_tester.keywords_kwonly_opt(a=1, b=2, c=3), (1, 2, 3))

    def test_posonly_keywords(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords(a=1, b=2)
        self.assertEqual(ac_tester.posonly_keywords(1, 2), (1, 2))
        self.assertEqual(ac_tester.posonly_keywords(1, b=2), (1, 2))

    def test_posonly_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(1, 2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly(a=1, b=2)
        self.assertEqual(ac_tester.posonly_kwonly(1, b=2), (1, 2))

    def test_posonly_keywords_kwonly(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly(a=1, b=2, c=3)
        self.assertEqual(ac_tester.posonly_keywords_kwonly(1, 2, c=3), (1, 2, 3))
        self.assertEqual(ac_tester.posonly_keywords_kwonly(1, b=2, c=3), (1, 2, 3))

    def test_posonly_keywords_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt(1)
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, 3, 4), (1, 2, 3, 4))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt(1, 2, c=3), (1, 2, 3, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt(a=1, b=2, c=3, d=4)
        self.assertEqual(ac_tester.posonly_keywords_opt(1, b=2, c=3, d=4), (1, 2, 3, 4))

    def test_posonly_opt_keywords_opt(self):
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, 3, 4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt(1, 2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt(a=1, b=2, c=3, d=4)

    def test_posonly_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(1, 2)
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2), (1, 2, None, None))
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_kwonly_opt(1, b=2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_kwonly_opt(a=1, b=2, c=3, d=4)

    def test_posonly_opt_kwonly_opt(self):
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_kwonly_opt(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_kwonly_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4))

    def test_posonly_keywords_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, 2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, b=2)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(1, 2, 3)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_kwonly_opt(a=1, b=2, c=3)
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, b=2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_kwonly_opt(1, 2, c=3, d=4, e=5), (1, 2, 3, 4, 5))

    def test_posonly_keywords_opt_kwonly_opt(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(1)
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2), (1, 2, None, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, b=2), (1, 2, None, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, 4)
        with self.assertRaises(TypeError):
            ac_tester.posonly_keywords_opt_kwonly_opt(a=1, b=2)
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, b=2, c=3), (1, 2, 3, None, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4, None))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, 3, d=4, e=5), (1, 2, 3, 4, 5))
        self.assertEqual(ac_tester.posonly_keywords_opt_kwonly_opt(1, 2, c=3, d=4, e=5), (1, 2, 3, 4, 5))

    def test_posonly_opt_keywords_opt_kwonly_opt(self):
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1), (1, None, None, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2), (1, 2, None, None))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, b=2)
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, c=3), (1, 2, 3, None))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3, d=4), (1, 2, 3, 4))
        self.assertEqual(ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, c=3, d=4), (1, 2, 3, 4))
        with self.assertRaises(TypeError):
            ac_tester.posonly_opt_keywords_opt_kwonly_opt(1, 2, 3, 4)

    def test_keyword_only_parameter(self):
        with self.assertRaises(TypeError):
            ac_tester.keyword_only_parameter()
        with self.assertRaises(TypeError):
            ac_tester.keyword_only_parameter(1)
        self.assertEqual(ac_tester.keyword_only_parameter(a=1), (1,))

    def test_posonly_vararg(self):
        with self.assertRaises(TypeError):
            ac_tester.posonly_vararg()
        self.assertEqual(ac_tester.posonly_vararg(1, 2), (1, 2, ()))
        self.assertEqual(ac_tester.posonly_vararg(1, b=2), (1, 2, ()))
        self.assertEqual(ac_tester.posonly_vararg(1, 2, 3, 4), (1, 2, (3, 4)))

    def test_vararg_and_posonly(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg_and_posonly()
        with self.assertRaises(TypeError):
            ac_tester.vararg_and_posonly(1, b=2)
        self.assertEqual(ac_tester.vararg_and_posonly(1, 2, 3, 4), (1, (2, 3, 4)))

    def test_vararg(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg()
        with self.assertRaises(TypeError):
            ac_tester.vararg(1, b=2)
        self.assertEqual(ac_tester.vararg(1, 2, 3, 4), (1, (2, 3, 4)))

    def test_vararg_with_default(self):
        with self.assertRaises(TypeError):
            ac_tester.vararg_with_default()
        self.assertEqual(ac_tester.vararg_with_default(1, b=False), (1, (), False))
        self.assertEqual(ac_tester.vararg_with_default(1, 2, 3, 4), (1, (2, 3, 4), False))
        self.assertEqual(ac_tester.vararg_with_default(1, 2, 3, 4, b=True), (1, (2, 3, 4), True))

    def test_vararg_with_only_defaults(self):
        self.assertEqual(ac_tester.vararg_with_only_defaults(), ((), None))
        self.assertEqual(ac_tester.vararg_with_only_defaults(b=2), ((), 2))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, b=2), ((1, ), 2))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, 2, 3, 4), ((1, 2, 3, 4), None))
        self.assertEqual(ac_tester.vararg_with_only_defaults(1, 2, 3, 4, b=5), ((1, 2, 3, 4), 5))

    def test_gh_32092_oob(self):
        ac_tester.gh_32092_oob(1, 2, 3, 4, kw1=5, kw2=6)

    def test_gh_32092_kw_pass(self):
        ac_tester.gh_32092_kw_pass(1, 2, 3)

    def test_gh_99233_refcount(self):
        arg = '*A unique string is not referenced by anywhere else.*'
        arg_refcount_origin = sys.getrefcount(arg)
        ac_tester.gh_99233_refcount(arg)
        arg_refcount_after = sys.getrefcount(arg)
        self.assertEqual(arg_refcount_origin, arg_refcount_after)

    def test_gh_99240_double_free(self):
        expected_error = r'gh_99240_double_free\(\) argument 2 must be encoded string without null bytes, not str'
        with self.assertRaisesRegex(TypeError, expected_error):
            ac_tester.gh_99240_double_free('a', '\0b')

    def test_cloned_func_exception_message(self):
        incorrect_arg = -1  # f1() and f2() accept a single str
        with self.assertRaisesRegex(TypeError, "clone_f1"):
            ac_tester.clone_f1(incorrect_arg)
        with self.assertRaisesRegex(TypeError, "clone_f2"):
            ac_tester.clone_f2(incorrect_arg)

    def test_cloned_func_with_converter_exception_message(self):
        for name in "clone_with_conv_f1", "clone_with_conv_f2":
            with self.subTest(name=name):
                func = getattr(ac_tester, name)
                self.assertEqual(func(), name)


class PermutationTests(unittest.TestCase):
    """Test permutation support functions."""

    def test_permute_left_option_groups(self):
        expected = (
            (),
            (3,),
            (2, 3),
            (1, 2, 3),
        )
        data = list(zip([1, 2, 3]))  # Generate a list of 1-tuples.
        actual = tuple(clinic.permute_left_option_groups(data))
        self.assertEqual(actual, expected)

    def test_permute_right_option_groups(self):
        expected = (
            (),
            (1,),
            (1, 2),
            (1, 2, 3),
        )
        data = list(zip([1, 2, 3]))  # Generate a list of 1-tuples.
        actual = tuple(clinic.permute_right_option_groups(data))
        self.assertEqual(actual, expected)

    def test_permute_optional_groups(self):
        empty = {
            "left": (), "required": (), "right": (),
            "expected": ((),),
        }
        noleft1 = {
            "left": (), "required": ("b",), "right": ("c",),
            "expected": (
                ("b",),
                ("b", "c"),
            ),
        }
        noleft2 = {
            "left": (), "required": ("b", "c",), "right": ("d",),
            "expected": (
                ("b", "c"),
                ("b", "c", "d"),
            ),
        }
        noleft3 = {
            "left": (), "required": ("b", "c",), "right": ("d", "e"),
            "expected": (
                ("b", "c"),
                ("b", "c", "d"),
                ("b", "c", "d", "e"),
            ),
        }
        noright1 = {
            "left": ("a",), "required": ("b",), "right": (),
            "expected": (
                ("b",),
                ("a", "b"),
            ),
        }
        noright2 = {
            "left": ("a",), "required": ("b", "c"), "right": (),
            "expected": (
                ("b", "c"),
                ("a", "b", "c"),
            ),
        }
        noright3 = {
            "left": ("a", "b"), "required": ("c",), "right": (),
            "expected": (
                ("c",),
                ("b", "c"),
                ("a", "b", "c"),
            ),
        }
        leftandright1 = {
            "left": ("a",), "required": ("b",), "right": ("c",),
            "expected": (
                ("b",),
                ("a", "b"),  # Prefer left.
                ("a", "b", "c"),
            ),
        }
        leftandright2 = {
            "left": ("a", "b"), "required": ("c", "d"), "right": ("e", "f"),
            "expected": (
                ("c", "d"),
                ("b", "c", "d"),       # Prefer left.
                ("a", "b", "c", "d"),  # Prefer left.
                ("a", "b", "c", "d", "e"),
                ("a", "b", "c", "d", "e", "f"),
            ),
        }
        dataset = (
            empty,
            noleft1, noleft2, noleft3,
            noright1, noright2, noright3,
            leftandright1, leftandright2,
        )
        for params in dataset:
            with self.subTest(**params):
                left, required, right, expected = params.values()
                permutations = clinic.permute_optional_groups(left, required, right)
                actual = tuple(permutations)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
