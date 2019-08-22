from django.apps import AppConfig

from django_arduino_controller.apps import DjangoArduinoControllerConfig

from tensile_tester.tensile_tester_api import TensileTesterApi


class TensileTesterConfig(AppConfig):
    module_path = ".".join(__name__.split(".")[:-1])
    name = "tensile_tester"
    baseurl = "tensile_tester"

    data_dir = True

    def ready(self):
        DjangoArduinoControllerConfig.add_api(TensileTesterApi)
