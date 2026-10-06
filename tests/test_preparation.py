"""Synthetic software check only; no experimental data or GPU processing.
Run from the repository root: python tests/test_preparation.py
Requires NumPy and Pillow. Temporary inputs/outputs are removed on exit.
"""
from pathlib import Path
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image

GUI = Path(__file__).resolve().parents[1]

def run(script, *args, success=True):
    result = subprocess.run([sys.executable, str(GUI/script), *map(str,args)], capture_output=True, text=True)
    if (result.returncode == 0) != success:
        raise AssertionError(result.stdout + result.stderr)
    return result

with tempfile.TemporaryDirectory(prefix='stem-prep-test-') as tmp:
    base=Path(tmp); raw=base/'raw';raw.mkdir()
    header=bytearray(1024)
    struct.pack_into('<4i',header,0,4,3,3,2)
    struct.pack_into('<3i',header,28,4,3,3)
    struct.pack_into('<3f',header,40,4,3,3)
    struct.pack_into('<3f',header,52,90,90,90)
    struct.pack_into('<3i',header,64,1,2,3)
    header[208:212]=b'MAP ';header[212:216]=b'DA\0\0'
    data=np.arange(36,dtype='<f4').reshape(3,3,4)-17.5
    (raw/'example.mrc').write_bytes(header+data.tobytes())
    # Block order, ZValue order and angular order are intentionally distinct.
    records=[(2,0),(0,30),(1,-30)]
    (raw/'example.mdoc').write_text('PixelSpacing = 1\n\n'+''.join(f'[ZValue = {z}]\nTiltAngle = {a}\nSubFramePath = obsolete.tif\n\n' for z,a in records))
    original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}
    orders={'block':[0,30,-30], 'zvalue':[30,-30,0], 'tilt-ascending':[-30,0,30], 'tilt-descending':[30,0,-30]}
    for order,angles in orders.items():
        out=base/order
        args=['--input',raw,'--output',out,'--slice-order',order,'--output-dtype','preserve','--preview-count','3']
        preview=run('prepare_warp_tiltseries.py',*args,'--dry-run')
        assert not out.exists(), 'Dry run wrote output'
        assert 'previewing 3 of 3' in preview.stdout
        run('prepare_warp_tiltseries.py',*args)
        assert len(list((out/'frames').glob('*.tif')))==3
        for i,angle in enumerate(angles):
            with Image.open(out/'frames'/f'example_{angle:.1f}.tif') as im:
                np.testing.assert_array_equal(np.asarray(im),data[i])
        mdoc=out/'mdoc/example_warp.mdoc';text=mdoc.read_text()
        assert re.findall(r'\[ZValue = (\d+)\]',text)==['2','0','1']
        assert 'obsolete.tif' not in text
        for block in re.split(r'\[ZValue = \d+\]',text)[1:]:
            angle=float(re.search(r'TiltAngle = (.*)',block).group(1))
            path=re.search(r'SubFramePath = (.*)',block).group(1)
            assert path==f'frames/example_{angle:.1f}.tif'
            assert (out/path).exists()
        assert (out/'prepare_warp_summary.csv').exists()
        refusal=run('prepare_warp_tiltseries.py',*args,success=False)
        assert 'Refusing to overwrite' in refusal.stderr
        tlt=out/'angles.tlt'
        run('mdoc_to_tlt.py','--mdoc',mdoc,'--output',tlt,'--order',order)
        assert list(map(float,tlt.read_text().split()))==angles
        run('mdoc_to_tlt.py','--mdoc',mdoc,'--output',tlt,success=False)
        print(f'PASS {order}: dry run, pixel values, metadata paths/order, summary, TLT and overwrite refusal')
    assert original=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.iterdir()}
    print('PASS raw inputs unchanged')
print('All synthetic preparation checks passed. This is not scientific validation.')
