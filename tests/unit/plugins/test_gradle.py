# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright (C) 2016-2018 Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
from textwrap import dedent
from unittest import mock

import fixtures
from testtools.matchers import Equals, HasLength

from snapcraft.internal import errors
from snapcraft.plugins import gradle
from snapcraft.project import Project
from tests import unit


class GradlePluginBaseTest(unit.TestCase):
    def setUp(self):
        super().setUp()

        snapcraft_yaml_path = self.make_snapcraft_yaml(
            dedent(
                """\
            name: gradle-snap
            base: core18
        """
            )
        )

        self.project = Project(snapcraft_yaml_file_path=snapcraft_yaml_path)

        class Options:
            gradle_options = []
            gradle_output_dir = "build/libs"
            gradle_version = gradle._DEFAULT_GRADLE_VERSION
            gradle_version_checksum = gradle._DEFAULT_GRADLE_CHECKSUM
            gradle_openjdk_version = "11"

        self.options = Options()

        # unset http and https proxies.
        self.useFixture(fixtures.EnvironmentVariable("http_proxy", None))
        self.useFixture(fixtures.EnvironmentVariable("https_proxy", None))

        patcher = mock.patch("snapcraft.internal.common.run")
        self.run_mock = patcher.start()
        self.addCleanup(patcher.stop)

        patcher = mock.patch("snapcraft.internal.sources.Zip")
        self.zip_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def create_assets(self, plugin, use_gradlew=False):
        os.makedirs(plugin.sourcedir)

        if use_gradlew:
            open(os.path.join(plugin.sourcedir, "gradlew"), "w").close()

        fake_java_path = os.path.join(
            plugin.installdir,
            "usr",
            "lib",
            "jvm",
            "java-11-openjdk-amd64",
            "jre",
            "bin",
            "java",
        )
        os.makedirs(os.path.dirname(fake_java_path))
        open(fake_java_path, "w").close()

        gradle_zip_path = os.path.join(
            plugin.partdir,
            "gradle",
            "apache-gradle-{}-bin.tar.gz".format(plugin.options.gradle_version),
        )
        os.makedirs(os.path.dirname(gradle_zip_path))
        open(gradle_zip_path, "w").close()


class GradlePluginPropertiesTest(unit.TestCase):
    def test_schema(self):
        schema = gradle.GradlePlugin.schema()

        properties = schema["properties"]
        self.assertTrue(
            "gradle-options" in properties,
            'Expected "gradle-options" to be included in ' "properties",
        )

        gradle_options = properties["gradle-options"]

        self.assertTrue(
            "type" in gradle_options,
            'Expected "type" to be included in "gradle-options"',
        )
        self.assertThat(
            gradle_options["type"],
            Equals("array"),
            'Expected "gradle-options" "type" to be "array", but '
            'it was "{}"'.format(gradle_options["type"]),
        )

        self.assertTrue(
            "minitems" in gradle_options,
            'Expected "minitems" to be included in "gradle-options"',
        )
        self.assertThat(
            gradle_options["minitems"],
            Equals(1),
            'Expected "gradle-options" "minitems" to be 1, but '
            'it was "{}"'.format(gradle_options["minitems"]),
        )

        self.assertTrue(
            "uniqueItems" in gradle_options,
            'Expected "uniqueItems" to be included in "gradle-options"',
        )
        self.assertTrue(
            gradle_options["uniqueItems"],
            'Expected "gradle-options" "uniqueItems" to be "True"',
        )

        output_dir = properties["gradle-output-dir"]
        self.assertTrue(
            "type" in output_dir, 'Expected "type" to be included in "gradle-options"'
        )
        self.assertThat(
            output_dir["type"],
            Equals("string"),
            'Expected "gradle-options" "type" to be "string", '
            'but it was "{}"'.format(output_dir["type"]),
        )

    def test_get_pull_properties(self):
        expected_pull_properties = [
            "gradle-version",
            "gradle-version-checksum",
            "gradle-openjdk-version",
        ]
        resulting_pull_properties = gradle.GradlePlugin.get_pull_properties()

        self.assertThat(
            resulting_pull_properties, HasLength(len(expected_pull_properties))
        )

        for property in expected_pull_properties:
            self.assertIn(property, resulting_pull_properties)

    def test_get_build_properties(self):
        expected_build_properties = ["gradle-options", "gradle-output-dir"]
        resulting_build_properties = gradle.GradlePlugin.get_build_properties()

        self.assertThat(
            resulting_build_properties, HasLength(len(expected_build_properties))
        )

        for property in expected_build_properties:
            self.assertIn(property, resulting_build_properties)


class GradlePluginTest(GradlePluginBaseTest):
    def test_get_defaul_openjdk(self):
        self.options.gradle_openjdk_version = ""

        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.assertThat(plugin.stage_packages, Equals(["openjdk-11-jre-headless"]))
        self.assertThat(
            plugin.build_packages,
            Equals(["openjdk-11-jdk-headless", "ca-certificates-java"]),
        )

    def test_get_non_defaul_openjdk(self):
        self.options.gradle_openjdk_version = "8"

        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.assertThat(plugin.stage_packages, Equals(["openjdk-8-jre-headless"]))
        self.assertThat(
            plugin.build_packages,
            Equals(["openjdk-8-jdk-headless", "ca-certificates-java"]),
        )

    def test_build_gradlew(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin, use_gradlew=True)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.jar"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["./gradlew", "jar"], cwd=plugin.builddir, env=None
        )

    def test_build_gradle(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.jar"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["gradle", "jar"], cwd=plugin.builddir, env=mock.ANY
        )

    def test_build_war_gradle(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.war"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["gradle", "jar"], cwd=plugin.builddir, env=mock.ANY
        )

    def test_build_war_gradlew(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin, use_gradlew=True)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.war"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["./gradlew", "jar"], cwd=plugin.builddir, env=None
        )


class GradleProxyTestCase(GradlePluginBaseTest):

    scenarios = [
        (
            "http proxy url",
            dict(
                env_var=("http_proxy", "http://test_proxy"),
                expected_args=["-Dhttp.proxyHost=test_proxy"],
            ),
        ),
        (
            "http proxy url and port",
            dict(
                env_var=("http_proxy", "http://test_proxy:3000"),
                expected_args=["-Dhttp.proxyHost=test_proxy", "-Dhttp.proxyPort=3000"],
            ),
        ),
        (
            "authenticated http proxy url",
            dict(
                env_var=("http_proxy", "http://user:pass@test_proxy:3000"),
                expected_args=[
                    "-Dhttp.proxyHost=test_proxy",
                    "-Dhttp.proxyPort=3000",
                    "-Dhttp.proxyUser=user",
                    "-Dhttp.proxyPassword=pass",
                ],
            ),
        ),
        (
            "https proxy url",
            dict(
                env_var=("https_proxy", "https://test_proxy"),
                expected_args=["-Dhttps.proxyHost=test_proxy"],
            ),
        ),
        (
            "https proxy url and port",
            dict(
                env_var=("https_proxy", "https://test_proxy:3000"),
                expected_args=[
                    "-Dhttps.proxyHost=test_proxy",
                    "-Dhttps.proxyPort=3000",
                ],
            ),
        ),
        (
            "authenticated https proxy url",
            dict(
                env_var=("https_proxy", "http://user:pass@test_proxy:3000"),
                expected_args=[
                    "-Dhttps.proxyHost=test_proxy",
                    "-Dhttps.proxyPort=3000",
                    "-Dhttps.proxyUser=user",
                    "-Dhttps.proxyPassword=pass",
                ],
            ),
        ),
    ]

    def setUp(self):
        super().setUp()

        self.useFixture(fixtures.EnvironmentVariable(*self.env_var))

    def test_build_with_http_proxy_gradle(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.war"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["gradle"] + self.expected_args + ["jar"], cwd=plugin.builddir, env=mock.ANY
        )

    def test_build_with_http_proxy_gradlew(self):
        plugin = gradle.GradlePlugin("test-part", self.options, self.project)

        self.create_assets(plugin, use_gradlew=True)

        def side(l, **kwargs):
            os.makedirs(os.path.join(plugin.builddir, "build", "libs"))
            open(
                os.path.join(plugin.builddir, "build", "libs", "dummy.war"), "w"
            ).close()

        self.run_mock.side_effect = side

        plugin.build()

        self.run_mock.assert_called_once_with(
            ["./gradlew"] + self.expected_args + ["jar"], cwd=plugin.builddir, env=None
        )


class GradlePluginUnsupportedBase(GradlePluginBaseTest):
    def setUp(self):
        super().setUp()

        snapcraft_yaml_path = self.make_snapcraft_yaml(
            dedent(
                """\
            name: gradle-snap
            base: unsupported-base
        """
            )
        )

        self.project = Project(snapcraft_yaml_file_path=snapcraft_yaml_path)

    def test_unsupported_base_raises(self):
        self.assertRaises(
            errors.PluginBaseError,
            gradle.GradlePlugin,
            "test-part",
            self.options,
            self.project,
        )


class UnsupportedJDKVersionErrorTest(GradlePluginBaseTest):

    scenarios = (
        (
            "core16",
            dict(
                base="core16",
                version="11",
                expected_message=(
                    "The gradle-openjdk-version plugin property was set to '11'.\n"
                    "Valid values for the 'core16' base are: '8' or '9'."
                ),
            ),
        ),
        (
            "core18",
            dict(
                base="core18",
                version="9",
                expected_message=(
                    "The gradle-openjdk-version plugin property was set to '9'.\n"
                    "Valid values for the 'core18' base are: '11' or '8'."
                ),
            ),
        ),
    )

    def setUp(self):
        super().setUp()

        snapcraft_yaml_path = self.make_snapcraft_yaml(
            dedent(
                """\
            name: gradle-snap
            base: {base}
        """.format(
                    base=self.base
                )
            )
        )

        self.options.gradle_openjdk_version = self.version

        self.project = Project(snapcraft_yaml_file_path=snapcraft_yaml_path)

    def test_use_invalid_openjdk_version_fails(self):
        raised = self.assertRaises(
            gradle.UnsupportedJDKVersionError,
            gradle.GradlePlugin,
            "test-part",
            self.options,
            self.project,
        )
        self.assertThat(str(raised), Equals(self.expected_message))
