# Operator-owned synthetic acceptance: raster; nonce=409ecd883446435d99d3bd7c792beee1
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/raster-20261027-03/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/raster-20261027-03/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image
figure = Figure(figsize=(2,2),dpi=32)
canvas = FigureCanvasAgg(figure)
figure.add_subplot(111).plot([0,1,2],[0,1,0])
canvas.draw()
image = Image.fromarray(np.asarray(canvas.buffer_rgba()))
image.save('plot.png',format='PNG',compress_level=9)
write_summary([['width',image.width],['height',image.height]])
