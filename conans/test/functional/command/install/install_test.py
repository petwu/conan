import os
import platform
import textwrap
import unittest
from collections import OrderedDict

import pytest

from conans.client.tools.oss import detected_os
from conans.model.info import ConanInfo
from conans.model.ref import ConanFileReference, PackageReference
from conans.paths import CONANFILE, CONANFILE_TXT, CONANINFO
from conans.test.assets.cpp_test_files import cpp_hello_conan_files
from conans.test.utils.tools import NO_SETTINGS_PACKAGE_ID
from conans.test.utils.tools import TestClient, TestServer, GenConanfile
from conans.util.files import mkdir, rmdir


class InstallTest(unittest.TestCase):

    def setUp(self):
        self.client = TestClient()
        self.settings = ("-s os=Windows -s compiler='Visual Studio' -s compiler.version=12 "
                         "-s arch=x86 -s compiler.runtime=MD")

    def test_not_found_package_dirty_cache(self):
        # Conan does a lock on the cache, and even if the package doesn't exist
        # left a trailing folder with the filelocks. This test checks
        # it will be cleared
        client = TestClient(default_server_user=True)
        client.save({"conanfile.py": GenConanfile("Hello", "0.1")})
        client.run("create . lasote/testing")
        client.run("upload * --all --confirm")
        client.run('remove "*" -f')
        client.run("install hello/0.1@lasote/testing", assert_error=True)
        self.assertIn("Unable to find 'hello/0.1@lasote/testing'", client.out)
        # This used to fail in Windows, because of the trailing lock
        client.run("remove * -f")
        client.run("install Hello/0.1@lasote/testing")

    def test_install_reference_txt(self):
        # Test to check the "conan install <path> <reference>" command argument
        client = TestClient()
        client.save({"conanfile.txt": ""})
        client.run("info .")
        self.assertIn("conanfile.txt", str(client.out).splitlines())

    def test_install_reference_error(self):
        # Test to check the "conan install <path> <reference>" command argument
        client = TestClient()
        client.run("install Pkg/0.1@myuser/testing user/testing", assert_error=True)
        self.assertIn("ERROR: A full reference was provided as first argument", client.out)

    def test_install_reference(self):
        # Test to check the "conan install <path> <reference>" command argument
        client = TestClient()
        conanfile = """from conans import ConanFile
class Pkg(ConanFile):
    def build(self):
        self.output.info("REF: %s, %s, %s, %s" % (self.name, self.version, self.user, self.channel))
"""
        client.save({"conanfile.py": conanfile})
        client.run("build . --name=Pkg --version=0.1 --user=myuser --channel=testing")
        self.assertIn("REF: Pkg, 0.1, myuser, testing", client.out)
        client.run("info . --name=Pkg --version=0.1 --user=myuser --channel=testing")
        self.assertIn("Pkg/0.1@myuser/testing", client.out)

        # Trying with partial name
        conanfile = conanfile + "    name = 'Other'\n"
        client.save({"conanfile.py": conanfile})
        # passing the wrong package name raises
        client.run("install . Pkg/0.1@myuser/testing", assert_error=True)
        self.assertIn("ERROR: Package recipe with name Pkg!=Other", client.out)
        # Partial reference works
        client.run("build . --version=0.1 --user=myuser --channel=testing")
        self.assertIn("REF: Other, 0.1, myuser, testing", client.out)
        # And also full reference matching
        client.run("build . --name=Other --version=0.1 --user=myuser --channel=testing")
        self.assertIn("REF: Other, 0.1, myuser, testing", client.out)

        # Trying with partial name and version
        conanfile = conanfile + "    version = '0.2'\n"
        client.save({"conanfile.py": conanfile})
        # passing the wrong package name raises
        client.run("install . Other/0.1@myuser/testing", assert_error=True)
        self.assertIn("ERROR: Package recipe with version 0.1!=0.2", client.out)
        # Partial reference works
        client.run("build . --user=myuser --channel=testing")
        self.assertIn("REF: Other, 0.2, myuser, testing", client.out)
        # And also full reference matching
        client.run("build . --name=Other --version=0.2 --user=myuser --channel=testing")
        self.assertIn("REF: Other, 0.2, myuser, testing", client.out)

    def test_four_subfolder_install(self):
        # https://github.com/conan-io/conan/issues/3950
        conanfile = ""
        self.client.save({"path/to/sub/folder/conanfile.txt": conanfile})
        # If this doesn't, fail, all good
        self.client.run("install path/to/sub/folder")

    def test_install_system_requirements(self):
        client = TestClient(servers={"default": TestServer()},
                            users={"default": [("lasote", "mypass")]})
        client.save({"conanfile.py": """from conans import ConanFile
class MyPkg(ConanFile):
    def system_requirements(self):
        self.output.info("Running system requirements!!")
"""})
        client.run("install .")
        self.assertIn("Running system requirements!!", client.out)
        client.run("export . Pkg/0.1@lasote/testing")
        client.run("install Pkg/0.1@lasote/testing --build")
        self.assertIn("Running system requirements!!", client.out)
        client.run("upload * --all --confirm")
        client.run('remove "*" -f')
        client.run("install Pkg/0.1@lasote/testing")
        self.assertIn("Running system requirements!!", client.out)

    def test_install_transitive_pattern(self):
        # Make sure a simple conan install doesn't fire package_info() so self.package_folder breaks
        client = TestClient()
        client.save({"conanfile.py": """from conans import ConanFile
class Pkg(ConanFile):
    options = {"shared": [True, False, "header"]}
    default_options = "shared=False"
    def package_info(self):
        self.output.info("PKG OPTION: %s" % self.options.shared)
"""})
        client.run("create . Pkg/0.1@user/testing -o shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        client.save({"conanfile.py": """from conans import ConanFile
class Pkg(ConanFile):
    requires = "Pkg/0.1@user/testing"
    options = {"shared": [True, False, "header"]}
    default_options = "shared=False"
    def package_info(self):
        self.output.info("PKG2 OPTION: %s" % self.options.shared)
"""})

        client.run("create . Pkg2/0.1@user/testing -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: True", client.out)
        client.run("install Pkg2/0.1@user/testing -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: True", client.out)
        # Priority of non-scoped options
        client.run("create . Pkg2/0.1@user/testing -o shared=header -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        client.run("install Pkg2/0.1@user/testing -o shared=header -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        # Prevalence of exact named option
        client.run("create . Pkg2/0.1@user/testing -o *:shared=True -o Pkg2:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        client.run("install Pkg2/0.1@user/testing -o *:shared=True -o Pkg2:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        # Prevalence of exact named option reverse
        client.run("create . Pkg2/0.1@user/testing -o *:shared=True -o Pkg:shared=header "
                   "--build=missing")
        self.assertIn("Pkg/0.1@user/testing: Calling build()", client.out)
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: header", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: True", client.out)
        client.run("install Pkg2/0.1@user/testing -o *:shared=True -o Pkg:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: header", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: True", client.out)
        # Prevalence of alphabetical pattern
        client.run("create . Pkg2/0.1@user/testing -o *:shared=True -o Pkg2*:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        client.run("install Pkg2/0.1@user/testing -o *:shared=True -o Pkg2*:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        # Prevalence of alphabetical pattern, opposite order
        client.run("create . Pkg2/0.1@user/testing -o Pkg2*:shared=header -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        client.run("install Pkg2/0.1@user/testing -o Pkg2*:shared=header -o *:shared=True")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: True", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        # Prevalence and override of alphabetical pattern
        client.run("create . Pkg2/0.1@user/testing -o *:shared=True -o Pkg*:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: header", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)
        client.run("install Pkg2/0.1@user/testing -o *:shared=True -o Pkg*:shared=header")
        self.assertIn("Pkg/0.1@user/testing: PKG OPTION: header", client.out)
        self.assertIn("Pkg2/0.1@user/testing: PKG2 OPTION: header", client.out)

    def test_install_package_folder(self):
        # Make sure a simple conan install doesn't fire package_info() so self.package_folder breaks
        client = TestClient()
        client.save({"conanfile.py": textwrap.dedent("""\
            from conans import ConanFile
            import os
            class Pkg(ConanFile):
                def package_info(self):
                    self.dummy_doesnt_exist_not_break
                    self.output.info("Hello")
                    self.env_info.PATH = os.path.join(self.package_folder, "bin")
            """)})
        client.run("install .")
        self.assertNotIn("Hello", client.out)

    def _create(self, number, version, deps=None, export=True, no_config=False, settings=None):
        files = cpp_hello_conan_files(number, version, deps, build=False, config=not no_config,
                                      settings=settings)

        self.client.save(files, clean_first=True)
        if export:
            self.client.run("export . lasote/stable")

    def test_install_error_never(self):
        self._create("Hello0", "0.1", export=False)
        self.client.run("install . --build never --build missing", assert_error=True)
        self.assertIn("ERROR: --build=never not compatible with other options", self.client.out)
        self.client.run("install conanfile.py --build never --build Hello", assert_error=True)
        self.assertIn("ERROR: --build=never not compatible with other options", self.client.out)

    def test_install_combined(self):
        self._create("Hello0", "0.1")
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"])
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"], export=False)
        self.client.run("install . %s --build=missing" % self.settings)

        self.client.run("install . %s --build=missing --build Hello1" % self.settings)
        self.assertIn("Hello0/0.1@lasote/stable: Already installed!", self.client.out)
        self.assertIn("Hello1/0.1@lasote/stable: Forced build from source", self.client.out)

    def test_install_transitive_cache(self):
        self._create("Hello0", "0.1")
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"])
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"])
        self.client.run("install Hello2/0.1@lasote/stable %s --build=missing" % self.settings)
        self.assertIn("Hello0/0.1@lasote/stable: Generating the package", self.client.out)
        self.assertIn("Hello1/0.1@lasote/stable: Generating the package", self.client.out)
        self.assertIn("Hello2/0.1@lasote/stable: Generating the package", self.client.out)

    def test_partials(self):
        self._create("Hello0", "0.1")
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"])
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"], export=False)

        self.client.run("install . %s --build=missing" % self.settings)

        self.client.run("install ./ %s --build=Bye" % self.settings)
        self.assertIn("No package matching 'Bye' pattern", self.client.out)

        for package in ["Hello0", "Hello1"]:
            self.client.run("install . %s --build=%s" % (self.settings, package))
            self.assertNotIn("No package matching", self.client.out)

    def test_reuse(self):
        self._create("Hello0", "0.1")
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"])
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"], export=False)

        for lang, id0, id1 in [(0, "2e38bbc2c3ef1425197c8e2ffa8532894c347d26",
                                   "44671ecdd9c606eb7166f2197ab50be8d36a3c3b"),
                               (1, "8b964e421a5b7e48b7bc19b94782672be126be8b",
                                   "3eeab577a3134fa3afdcd82881751789ec48e08f")]:

            self.client.run("install . -o language=%d %s --build missing" % (lang, self.settings))
            self.assertIn("Configuration:[settings]", "".join(str(self.client.out).splitlines()))

            ref = ConanFileReference.loads("Hello0/0.1@lasote/stable")

            hello0 = self.client.cache.package_layout(ref).package(PackageReference(ref, id0))
            hello0_info = os.path.join(hello0, CONANINFO)
            hello0_conan_info = ConanInfo.load_file(hello0_info)
            self.assertEqual(lang, hello0_conan_info.options.language)

            pref1 = PackageReference(ConanFileReference.loads("Hello1/0.1@lasote/stable"), id1)
            hello1 = self.client.cache.package_layout(pref1.ref).package(pref1)
            hello1_info = os.path.join(hello1, CONANINFO)
            hello1_conan_info = ConanInfo.load_file(hello1_info)
            self.assertEqual(lang, hello1_conan_info.options.language)

    def test_upper_option(self):
        self._create("Hello0", "0.1", no_config=True)
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"], no_config=True)
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"], export=False, no_config=True)

        self.client.run("install conanfile.py -o Hello2:language=1 -o Hello1:language=0 "
                        "-o Hello0:language=1 %s --build missing" % self.settings)

        ref = ConanFileReference.loads("Hello0/0.1@lasote/stable")

        pref = PackageReference(ref, "8b964e421a5b7e48b7bc19b94782672be126be8b")
        hello0 = self.client.cache.package_layout(ref).package(pref)

        hello0_info = os.path.join(hello0, CONANINFO)
        hello0_conan_info = ConanInfo.load_file(hello0_info)
        self.assertEqual(1, hello0_conan_info.options.language)

        pref1 = PackageReference(ConanFileReference.loads("Hello1/0.1@lasote/stable"),
                                 "44671ecdd9c606eb7166f2197ab50be8d36a3c3b")
        hello1 = self.client.cache.package_layout(pref1.ref).package(pref1)
        hello1_info = os.path.join(hello1, CONANINFO)
        hello1_conan_info = ConanInfo.load_file(hello1_info)
        self.assertEqual(0, hello1_conan_info.options.language)

    def test_inverse_upper_option(self):
        self._create("Hello0", "0.1", no_config=True)
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"], no_config=True)
        self._create("Hello2", "0.1", ["Hello1/0.1@lasote/stable"], export=False, no_config=True)

        self.client.run("install . -o language=0 -o Hello1:language=1 -o Hello0:language=0 %s "
                        "--build missing" % self.settings)
        ref = ConanFileReference.loads("Hello0/0.1@lasote/stable")
        pref = PackageReference(ref, "2e38bbc2c3ef1425197c8e2ffa8532894c347d26")
        hello0 = self.client.cache.package_layout(ref).package(pref)

        hello0_info = os.path.join(hello0, CONANINFO)
        hello0_conan_info = ConanInfo.load_file(hello0_info)
        self.assertEqual("language=0\nstatic=True", hello0_conan_info.options.dumps())

        pref1 = PackageReference(ConanFileReference.loads("Hello1/0.1@lasote/stable"),
                                 "3eeab577a3134fa3afdcd82881751789ec48e08f")
        hello1 = self.client.cache.package_layout(pref1.ref).package(pref1)
        hello1_info = os.path.join(hello1, CONANINFO)
        hello1_conan_info = ConanInfo.load_file(hello1_info)
        self.assertEqual("language=1\nstatic=True", hello1_conan_info.options.dumps())

    def test_upper_option_txt(self):
        self._create("Hello0", "0.1", no_config=True)
        self._create("Hello1", "0.1", ["Hello0/0.1@lasote/stable"], no_config=True)

        files = cpp_hello_conan_files("Hello2", "0.1", ["Hello1/0.1@lasote/stable"])
        files.pop(CONANFILE)
        files[CONANFILE_TXT] = """[requires]
        Hello1/0.1@lasote/stable

        [options]
        Hello0:language=1
        Hello1:language=0
        """
        self.client.save(files, clean_first=True)

        self.client.run("install . %s --build missing" % self.settings)
        ref = ConanFileReference.loads("Hello0/0.1@lasote/stable")
        pref = PackageReference(ref, "8b964e421a5b7e48b7bc19b94782672be126be8b")
        hello0 = self.client.cache.package_layout(ref).package(pref)
        hello0_info = os.path.join(hello0, CONANINFO)
        hello0_conan_info = ConanInfo.load_file(hello0_info)
        self.assertEqual(1, hello0_conan_info.options.language)

        pref1 = PackageReference(ConanFileReference.loads("Hello1/0.1@lasote/stable"),
                                 "44671ecdd9c606eb7166f2197ab50be8d36a3c3b")
        hello1 = self.client.cache.package_layout(pref1.ref).package(pref1)
        hello1_info = os.path.join(hello1, CONANINFO)
        hello1_conan_info = ConanInfo.load_file(hello1_info)
        self.assertEqual(0, hello1_conan_info.options.language)

    @pytest.mark.tool_compiler
    def test_cross_platform_msg(self):
        # Explicit with os_build and os_arch settings
        message = "Cross-build from 'Linux:x86_64' to 'Windows:x86_64'"
        self._create("Hello0", "0.1", settings='"os_build", "os", "arch_build", "arch", "compiler"')
        self.client.run("install Hello0/0.1@lasote/stable -s os_build=Linux -s os=Windows",
                        assert_error=True)
        self.assertIn(message, self.client.out)

        # Implicit detection when not available (retrocompatibility)
        bad_os = "Linux" if platform.system() != "Linux" else "Macos"
        message = "Cross-build from '%s:x86_64' to '%s:x86_64'" % (detected_os(), bad_os)
        self._create("Hello0", "0.1")
        self.client.run("install Hello0/0.1@lasote/stable -s os=%s" % bad_os, assert_error=True)
        self.assertIn(message, self.client.out)

    def test_install_cwd(self):
        client = TestClient()
        client.save({"conanfile.py": GenConanfile("Hello", "0.1").with_setting("os")})
        client.run("export . lasote/stable")
        client.save({"conanfile.txt": "[requires]\nHello/0.1@lasote/stable"}, clean_first=True)

        client.run("install . --build=missing -s os=Windows -s os_build=Windows "
                   "--install-folder=win_dir")
        self.assertIn("Hello/0.1@lasote/stable from local cache", client.out)
        self.assertIn("os=Windows", client.out)
        self.assertNotIn("os=Macos", client.out)
        client.run("install . --build=missing -s os=Macos -s os_build=Macos "
                   "--install-folder=os_dir")
        self.assertNotIn("os=Windows", client.out)
        self.assertIn("os=Macos", client.out)

    def test_install_reference_not_conanbuildinfo(self):
        client = TestClient()
        client.save({"conanfile.py": GenConanfile("Hello", "0.1").with_setting("os")})
        client.run("create . conan/stable")
        client.save({}, clean_first=True)
        client.run("install Hello/0.1@conan/stable")
        self.assertFalse(os.path.exists(os.path.join(client.current_folder, "conanbuildinfo.txt")))

    def test_install_with_profile(self):
        # Test for https://github.com/conan-io/conan/pull/2043
        conanfile = textwrap.dedent("""
            from conans import ConanFile
            class TestConan(ConanFile):
                settings = "os"
                def requirements(self):
                    self.output.info("PKGOS=%s" % self.settings.os)
            """)
        client = TestClient()
        client.save({"conanfile.py": conanfile})
        client.run("profile new myprofile")
        client.run("profile update settings.os=Linux myprofile")
        client.run("install . -pr=myprofile --build")
        self.assertIn("PKGOS=Linux", client.out)
        mkdir(os.path.join(client.current_folder, "myprofile"))
        client.run("install . -pr=myprofile")
        client.run("profile new myotherprofile")
        client.run("profile update settings.os=FreeBSD myotherprofile")
        client.run("install . -pr=myotherprofile")
        self.assertIn("PKGOS=FreeBSD", client.out)
        client.save({"myotherprofile": "Some garbage without sense [garbage]"})
        client.run("install . -pr=myotherprofile")
        self.assertIn("PKGOS=FreeBSD", client.out)
        client.run("install . -pr=./myotherprofile", assert_error=True)
        self.assertIn("Error while parsing line 0", client.out)

    def test_install_with_path_errors(self):
        client = TestClient()

        # Install without path param not allowed
        client.run("install", assert_error=True)
        self.assertIn("ERROR: Exiting with code: 2", client.out)

        # Path with wrong conanfile.txt path
        client.run("install not_real_dir/conanfile.txt --install-folder subdir", assert_error=True)
        self.assertIn("Conanfile not found", client.out)

        # Path with wrong conanfile.py path
        client.run("install not_real_dir/conanfile.py --install-folder build", assert_error=True)
        self.assertIn("Conanfile not found", client.out)

    def test_install_broken_reference(self):
        client = TestClient(default_server_user=True)
        client.save({"conanfile.py": GenConanfile()})
        client.run("export . Hello/0.1@lasote/stable")
        client.run("remote add_ref Hello/0.1@lasote/stable default")
        ref = ConanFileReference.loads("Hello/0.1@lasote/stable")
        # Because the folder is removed, the metadata is removed and the
        # origin remote is lost
        rmdir(os.path.join(client.cache.package_layout(ref).base_folder()))
        client.run("install Hello/0.1@lasote/stable", assert_error=True)
        self.assertIn("ERROR: Unable to find 'Hello/0.1@lasote/stable' in remotes", client.out)

        # If it was associated, it has to be desasociated
        client.run("remote remove_ref Hello/0.1@lasote/stable")
        client.run("install Hello/0.1@lasote/stable", assert_error=True)
        self.assertIn("ERROR: Unable to find 'Hello/0.1@lasote/stable' in remotes", client.out)

    def test_install_argument_order(self):
        # https://github.com/conan-io/conan/issues/2520

        conanfile_boost = textwrap.dedent("""
            from conans import ConanFile
            class BoostConan(ConanFile):
                name = "boost"
                version = "0.1"
                options = {"shared": [True, False]}
                default_options = "shared=True"
            """)
        conanfile = GenConanfile().with_require("boost/0.1@conan/stable")
        client = TestClient()
        client.save({"conanfile.py": conanfile,
                     "conanfile_boost.py": conanfile_boost})
        client.run("create conanfile_boost.py conan/stable")
        client.run("install . -o boost:shared=True --build=missing")
        output_0 = "%s" % client.out
        client.run("install . -o boost:shared=True --build missing")
        output_1 = "%s" % client.out
        client.run("install -o boost:shared=True . --build missing")
        output_2 = "%s" % client.out
        client.run("install -o boost:shared=True --build missing .")
        output_3 = "%s" % client.out
        self.assertNotIn("ERROR", output_3)
        self.assertEqual(output_0, output_1)
        self.assertEqual(output_1, output_2)
        self.assertEqual(output_2, output_3)

        client.run("install -o boost:shared=True --build boost . --build missing")
        output_4 = "%s" % client.out
        client.run("install -o boost:shared=True --build missing --build boost .")
        output_5 = "%s" % client.out
        self.assertEqual(output_4, output_5)

    def test_install_anonymous(self):
        # https://github.com/conan-io/conan/issues/4871
        client = TestClient(default_server_user=True)
        client.save({"conanfile.py": GenConanfile("Pkg", "0.1")})
        client.run("create . lasote/testing")
        client.run("upload * --confirm --all")

        client2 = TestClient(servers=client.servers, users={})
        client2.run("install Pkg/0.1@lasote/testing")
        self.assertIn("Pkg/0.1@lasote/testing: Package installed", client2.out)

    def test_install_without_ref(self):
        client = TestClient(default_server_user=True)

        client.save({"conanfile.py": GenConanfile("lib", "1.0")})
        client.run('create .')
        self.assertIn("lib/1.0: Package '{}' created".format(NO_SETTINGS_PACKAGE_ID), client.out)

        client.run('upload lib/1.0 -c --all')
        self.assertIn("Uploaded conan recipe 'lib/1.0' to 'default'", client.out)

        client.run('remove "*" -f')

        # This fails, Conan thinks this is a path
        client.run('install lib/1.0', assert_error=True)
        fake_path = os.path.join(client.current_folder, "lib", "1.0")
        self.assertIn("Conanfile not found at {}".format(fake_path), client.out)

        # Try this syntax to upload too
        client.run('install lib/1.0@')
        client.run('upload lib/1.0@ -c --all')

    def test_install_disabled_remote(self):
        client = TestClient(default_server_user=True)
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . Pkg/0.1@lasote/testing")
        client.run("upload * --confirm --all -r default")
        client.run("remote disable default")
        client.run("install Pkg/0.1@lasote/testing -r default", assert_error=True)
        self.assertIn("ERROR: Remote 'default' is disabled", client.out)
        client.run("remote enable default")
        client.run("install Pkg/0.1@lasote/testing -r default")
        client.run("remote disable default")
        client.run("install Pkg/0.1@lasote/testing --update", assert_error=True)
        self.assertIn("ERROR: Remote 'default' is disabled", client.out)

    def test_install_skip_disabled_remote(self):
        client = TestClient(servers=OrderedDict({"default": TestServer(),
                                                 "server2": TestServer(),
                                                 "server3": TestServer()}),
                            users={"default": [("lasote", "mypass")],
                                   "server3": [("lasote", "mypass")]})
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . Pkg/0.1@lasote/testing")
        client.run("upload * --confirm --all -r default")
        client.run("upload * --confirm --all -r server3")
        client.run("remove * -f")
        client.run("remote disable default")
        client.run("install Pkg/0.1@lasote/testing", assert_error=False)
        self.assertNotIn("Trying with 'default'...", client.out)

    def test_install_version_range_reference(self):
        # https://github.com/conan-io/conan/issues/5905
        client = TestClient()
        client.save({"conanfile.py": GenConanfile()})
        client.run("create . pkg/0.1@user/channel")
        client.run("install pkg/[*]@user/channel")
        self.assertIn("pkg/0.1@user/channel from local cache - Cache", client.out)
        client.run("install pkg/[0.*]@user/channel")
        self.assertIn("pkg/0.1@user/channel from local cache - Cache", client.out)
