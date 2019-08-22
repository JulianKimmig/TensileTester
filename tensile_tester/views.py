# Create your views here.
import json
import logging
import os
import time

import numpy as np
import pandas as pd
from django.shortcuts import render, redirect
from django.utils.safestring import mark_safe
from django.views import View
from plug_in_django.manage import CONFIG

from tensile_tester.apps import TensileTesterConfig
from tensile_tester.tensile_tester_api import TensileTesterApi
from arduino_board_collection.boards.sensor_boards.force.tesile_test_board.tesile_test_board import TensileTestBoard
from django_arduino_controller.apps import DjangoArduinoControllerConfig
from .models import TensileTestForm, TensileTest
import matplotlib.pyplot as plt

mpl_logger = logging.getLogger("matplotlib")
mpl_logger.setLevel(logging.WARNING)


def index(request):
    tensile_tests = TensileTest.objects.all()
    return render(
        request,
        "tensile_tester_index.html"
        , {'tensile_tests': tensile_tests}
    )


BOARDDATASTREAMRECEIVER = None


class NewRoutine(View):
    def get(self, request):
        return render(request, "tensile_tester_routine.html")


def calibrate(request):
    return render(request, "tensile_tester_calibrate.html")


tensilertesterapi = None


def get_tensilertesterapi():
    global tensilertesterapi
    if tensilertesterapi is None:
        from django.apps import apps
        tensilertesterapi = apps.get_app_config('django_arduino_controller').get_api(TensileTesterApi)
    return tensilertesterapi


class NewMeasurement(View):
    def get(self, request):
        tensilertesterapi = get_tensilertesterapi()
        status = tensilertesterapi.get_status()
        if not status['status']:
            if status['code'] in [2,3]:
                return redirect('tensile_tester:running_measurement')
            return redirect('tensile_tester:index')

        form = TensileTestForm()
        return render(request, "tensile_tester_measurement.html", {'form': form})

    def post(self, request):
        tensilertesterapi = get_tensilertesterapi()
        post = request.POST.copy()
        board: TensileTestBoard = tensilertesterapi.linked_boards[0]
        post['scale'] = board.scale
        post['offset'] = board.offset

        print(post)
        pause_positions=''.join(c for c in post.get("pause_positions","") if c in "0123456789.,-")
        print(pause_positions)
        pause_positions = sorted([float(n) for n in pause_positions.split(",") if len(n)>0])
        print(pause_positions)
        post['pause_positions'] = json.dumps(pause_positions)

        form = TensileTestForm(post)
        if form.is_valid():
            tensile_test = form.save()
            CONFIG.put(TensileTesterConfig.name, "models", "TensileTest", "maximum_force",
                       value=tensile_test.maximum_force)
            CONFIG.put(TensileTesterConfig.name, "models", "TensileTest", "maximum_speed",
                       value=tensile_test.maximum_speed)
            CONFIG.put(TensileTesterConfig.name, "models", "TensileTest", "maximum_strain",
                       value=tensile_test.maximum_strain)
            CONFIG.put(TensileTesterConfig.name, "models", "TensileTest", "specimen_length",
                       value=tensile_test.specimen_length)
            CONFIG.put(TensileTesterConfig.name, "models", "TensileTest", "wobble_count",
                       value=tensile_test.wobble_count)
            test_id = tensile_test.id

            def _result(time_data, stress_strain_data):
                tensile_test = TensileTest.objects.get(id=test_id)
                regname = ''.join(
                    c if c in '-_()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' else "_" for c in
                    tensile_test.name)
                plt.figure()
                plt.plot(stress_strain_data["strain"].values, stress_strain_data["stress"].values, label='stress')
                image_path = os.path.join(
                    tensile_test.image.storage.location,
                    "tensile_test_{}_{}_stress_strain.png".format(tensile_test.id, regname),
                )
                plt.xlabel('strain [%]')
                plt.ylabel('stress [N]')
                plt.savefig(image_path)
                plt.close()

                time_data.insert(0, 'time', time_data.index)
                time_data.index = np.arange(len(time_data.index))

                header_dict = dict(
                    name=tensile_test.name,
                    date=tensile_test.updated_at,
                    offset=tensile_test.offset,
                    scale=tensile_test.scale,
                    maximum_force=tensile_test.maximum_force,
                    maximum_speed=tensile_test.maximum_speed,
                    maximum_strain=tensile_test.maximum_strain,
                    specimen_length=tensile_test.specimen_length,
                    pause_positions=tensile_test.pause_positions,
                )
                header = ["#{}={}".format(key, value)
                          for key, value in header_dict.items()
                          ]
                file = os.path.join(
                    tensile_test.data.storage.location,
                    "tensile_test_{}_{}.csv".format(tensile_test.id, regname),
                )
                with open(file, 'w+') as f:
                    for line in header:
                        f.write(line)
                        f.write("\n")
                    for line in pd.concat([time_data, stress_strain_data], axis=1, sort=False).to_csv(index=False,
                                                                                                      line_terminator='\n'):
                        f.write(line)
                tensile_test.image = os.path.basename(image_path)
                tensile_test.data = os.path.basename(file)
                tensile_test.save()

            tensilertesterapi.run_test(maximum_force=tensile_test.maximum_force, offset=tensile_test.offset,
                                       scale=tensile_test.scale, maximum_strain=tensile_test.maximum_strain,
                                       minimum_find_wobble_count=tensile_test.wobble_count,
                                       specimen_length=tensile_test.specimen_length,
                                       maximum_speed=tensile_test.maximum_speed, on_finish=_result,
                                       pause_positions=pause_positions
                                       )
            time.sleep(0.1)
            return redirect('tensile_tester:running_measurement')
        return render(request, "tensile_tester_measurement.html", {'form': form})


def running_measurement(request):
    tensilertesterapi = get_tensilertesterapi()
    status = tensilertesterapi.get_status()
    if not status['code'] in [2,3]:
        return redirect('tensile_tester:index')

    return render(request, "tensile_tester_running_measurement.html")


def view_test(request, id):
    tensile_test = TensileTest.objects.get(id=id)
    form = TensileTestForm(instance=tensile_test)
    data = pd.read_csv(tensile_test.data.file, comment='#')
    return render(request, "tensile_tester_view_test.html", dict(test=tensile_test,
                                                                 data=mark_safe(
                                                                     json.dumps(dict(time=data['time'].tolist(),
                                                                                     position=data['position'].tolist(),
                                                                                     force=data['force'].tolist(),
                                                                                     strain=data['strain'].tolist(),
                                                                                     stress=data['stress'].tolist()))),
                                                                 form=form,
                                                                 ))
