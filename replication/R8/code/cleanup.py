from common import *
import shutil
assert json.loads((R/'meta/DELIVERY_COMPLETE.json').read_text())['status']=='PASS'
assert T==Path('/Volumes/Extreme SSD/T9/_tmp/288')
shutil.rmtree(T)
print('Removed task-owned rebuildable intermediates:',T)
