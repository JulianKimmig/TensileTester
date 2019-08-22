from django.core.files.storage import FileSystemStorage
from django.db import models
from django.forms import ModelForm, HiddenInput, CharField, TextInput
from plug_in_django.manage import CONFIG

from tensile_tester.apps import TensileTesterConfig

# Create your models here.
tensile_test_upload_storage = FileSystemStorage(
    location=TensileTesterConfig.data_dir, base_url=TensileTesterConfig.data_dir_url
)

print(CONFIG)
class TensileTest(models.Model):
    name = models.CharField(max_length=255, unique=True)#
    offset = models.IntegerField(default=0)
    scale = models.FloatField()
    maximum_force = models.FloatField(default=CONFIG.get(TensileTesterConfig.name,"models","TensileTest","maximum_force",default=200))#
    maximum_speed = models.FloatField(default=CONFIG.get(TensileTesterConfig.name,"models","TensileTest","maximum_speed",default=0.1))#
    maximum_strain = models.FloatField(default=CONFIG.get(TensileTesterConfig.name,"models","TensileTest","maximum_strain",default=50))#
    wobble_count = models.IntegerField(default=CONFIG.get(TensileTesterConfig.name,"models","TensileTest","wobble_count",default=4))#
    pause_positions = models.CharField(null=True,max_length=255,default="[]")#
    specimen_length = models.FloatField(default=CONFIG.get(TensileTesterConfig.name,"models","TensileTest","specimen_length",default=20))#
    created_at = models.DateTimeField(auto_now_add=True)#
    updated_at = models.DateTimeField(auto_now=True)#
    data = models.FileField(storage=tensile_test_upload_storage, null=True)#
    image = models.FileField(storage=tensile_test_upload_storage, null=True)#

class TensileTestForm(ModelForm):
    pause_positions = CharField(label='Pause positions',widget=TextInput(attrs={'placeholder':'eg. 10.0,11.1,15'}), required=False)
    class Meta:
        model = TensileTest
        fields = ['name',
                  'maximum_force',
                  'maximum_strain',
                  'specimen_length',
                  'maximum_speed',
                  'pause_positions',
                  'wobble_count',
                  'offset',
                  'scale',
                  ]
        widgets = {'offset': HiddenInput(),'scale': HiddenInput()}
