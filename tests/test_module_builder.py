"""Tests for services.module_builder (ModuleBuilder)."""
import os
import pytest

from services.module_builder import ModuleBuilder, _sanitize, _to_class_name, BuildResult


@pytest.fixture
def builder(tmp_path, monkeypatch):
    """Return a ModuleBuilder in dry_run mode with temp dirs."""
    import services.module_builder as mb_mod
    monkeypatch.setattr(mb_mod, "_SERVICES_PY", str(tmp_path / "services"))
    monkeypatch.setattr(mb_mod, "_SERVICES_D",  str(tmp_path / "services.d"))
    monkeypatch.setattr(mb_mod, "_SHELL_PLUG",  str(tmp_path / "plugins"))
    monkeypatch.setattr(mb_mod, "_TESTS_DIR",   str(tmp_path / "tests"))
    os.makedirs(tmp_path / "services", exist_ok=True)
    os.makedirs(tmp_path / "services.d", exist_ok=True)
    os.makedirs(tmp_path / "plugins", exist_ok=True)
    os.makedirs(tmp_path / "tests", exist_ok=True)
    return ModuleBuilder()


class TestModuleBuilder:
    def test_scaffold_service_creates_files(self, builder, tmp_path):
        result = builder.scaffold_service("my_feature", description="Does things")
        assert result.success
        assert len(result.paths) == 3  # service + test + descriptor

    def test_scaffold_service_file_content(self, builder, tmp_path):
        builder.scaffold_service("alpha_svc")
        import services.module_builder as mb_mod
        svc_file = os.path.join(mb_mod._SERVICES_PY, "alpha_svc_service.py")
        assert os.path.isfile(svc_file)
        content = open(svc_file).read()
        assert "class AlphaSvcService" in content
        assert "def start" in content
        assert "def stop" in content

    def test_scaffold_service_test_file(self, builder, tmp_path):
        builder.scaffold_service("beta_svc")
        import services.module_builder as mb_mod
        test_file = os.path.join(mb_mod._TESTS_DIR, "test_beta_svc_service.py")
        assert os.path.isfile(test_file)
        content = open(test_file).read()
        assert "TestBetaSvcService" in content
        assert "test_start_stop" in content

    def test_scaffold_service_descriptor_file(self, builder, tmp_path):
        builder.scaffold_service("gamma_svc")
        import services.module_builder as mb_mod
        desc_file = os.path.join(mb_mod._SERVICES_D, "gamma_svc.service")
        assert os.path.isfile(desc_file)
        content = open(desc_file).read()
        assert "Name=gamma_svc" in content
        assert "Module=services.gamma_svc_service:GammaSvcService" in content

    def test_scaffold_service_no_test(self, builder, tmp_path):
        result = builder.scaffold_service("no_test_svc", with_test=False)
        assert result.success
        assert len(result.paths) == 2  # service + descriptor only

    def test_scaffold_service_no_descriptor(self, builder, tmp_path):
        result = builder.scaffold_service("no_desc_svc", with_descriptor=False)
        assert result.success
        assert len(result.paths) == 2  # service + test only

    def test_scaffold_service_duplicate_fails(self, builder, tmp_path):
        builder.scaffold_service("dup_svc")
        result2 = builder.scaffold_service("dup_svc")
        assert not result2.success
        assert len(result2.errors) > 0

    def test_scaffold_plugin(self, builder, tmp_path):
        result = builder.scaffold_plugin("my_plugin", description="A plugin")
        assert result.success
        assert len(result.paths) == 1

    def test_scaffold_plugin_content(self, builder, tmp_path):
        builder.scaffold_plugin("echo_cmd")
        import services.module_builder as mb_mod
        plugin_file = os.path.join(mb_mod._SHELL_PLUG, "echo_cmd.py")
        assert os.path.isfile(plugin_file)
        content = open(plugin_file).read()
        assert "def register" in content
        assert "def cmd_echo_cmd" in content

    def test_list_templates(self, builder):
        templates = builder.list_templates()
        assert "service" in templates
        assert "plugin" in templates

    def test_dry_run_no_files_written(self, tmp_path, monkeypatch):
        import services.module_builder as mb_mod
        monkeypatch.setattr(mb_mod, "_SERVICES_PY", str(tmp_path / "services"))
        monkeypatch.setattr(mb_mod, "_SERVICES_D",  str(tmp_path / "services.d"))
        monkeypatch.setattr(mb_mod, "_TESTS_DIR",   str(tmp_path / "tests"))
        mb = ModuleBuilder(dry_run=True)
        result = mb.scaffold_service("dry_run_svc")
        assert result.paths  # paths still populated
        svc_file = tmp_path / "services" / "dry_run_svc_service.py"
        assert not svc_file.exists()

    def test_event_published_on_success(self, tmp_path, monkeypatch):
        import services.module_builder as mb_mod
        monkeypatch.setattr(mb_mod, "_SERVICES_PY", str(tmp_path / "services"))
        monkeypatch.setattr(mb_mod, "_SERVICES_D",  str(tmp_path / "services.d"))
        monkeypatch.setattr(mb_mod, "_TESTS_DIR",   str(tmp_path / "tests"))
        os.makedirs(tmp_path / "services", exist_ok=True)
        os.makedirs(tmp_path / "services.d", exist_ok=True)
        os.makedirs(tmp_path / "tests", exist_ok=True)

        from kernel.event_bus import EventBus
        bus = EventBus()
        events = []
        bus.subscribe("MODULE_BUILT", lambda e: events.append(e))
        mb = ModuleBuilder(event_bus=bus)
        mb.scaffold_service("event_svc")
        # EventBus is queue-based — drain to deliver
        bus.drain()
        assert any(e.event_type == "MODULE_BUILT" for e in events)


class TestHelpers:
    def test_sanitize_basic(self):
        assert _sanitize("MyFeature") == "myfeature"

    def test_sanitize_spaces_to_underscore(self):
        assert _sanitize("my feature") == "my_feature"

    def test_sanitize_special_chars(self):
        assert _sanitize("my-feature!") == "my_feature"

    def test_sanitize_empty_raises(self):
        with pytest.raises(ValueError):
            _sanitize("")

    def test_to_class_name(self):
        assert _to_class_name("my_feature") == "MyFeature"
        assert _to_class_name("foo") == "Foo"
        assert _to_class_name("two_words") == "TwoWords"
