"""Regression checks without starting the Streamlit interface."""
import ast
from pathlib import Path
import re
import unittest

import fitz
import numpy as np
import pandas as pd

source = Path(__file__).resolve().parents[1] / 'pages' / 'kleventa.py'
namespace = dict(fitz=fitz, np=np, pd=pd, re=re)
module = ast.parse(source.read_text())
exec(compile(ast.Module(body=[n for n in module.body if isinstance(n, ast.FunctionDef)],
                        type_ignores=[]), str(source), 'exec'), namespace)


class KleventaTests(unittest.TestCase):
    def test_formats_duplicates_and_export(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                pdf = fitz.open()
                page = pdf.new_page()
                for y, values in [(100, [32.1, 33.2, 34.3, -2.0, 18.0, 19.0]),
                                  (125, [35.1, 36.2, 37.3, -3.0, 17.0, 18.0])]:
                    date = '30-09-2026' if legacy else '30/09/2026'
                    page.insert_text((30, y), date + (' ' if legacy else ' - ') + '08:04')
                    for x, value in zip([190, 255, 320, 385, 450, 515], values):
                        page.insert_text((x, y), f'{value:.1f}' + ('°C' if legacy else ''),
                                         fontname='heit' if legacy else 'helv', fontsize=10)
                data = pdf.tobytes()
                pdf.close()
                df = namespace['extract_temperature_data'](data)
                self.assertEqual(len(df), 2)
                self.assertEqual(df.Stock1.tolist(), [32.1, 35.1])
                results = {s: namespace['analyse_sensor'](df[s]) for s in ['Stock1', 'Stock2', 'Stock3']}
                output = namespace['create_corrected_pdf'](data, df, results)
                parsed = namespace['extract_temperature_data'](output)
                self.assertEqual(len(parsed), 2)
                for sensor in results:
                    np.testing.assert_array_equal(parsed[sensor], results[sensor]['corrected'])
                pd.testing.assert_frame_equal(df[['Outside', 'Water', 'Inlet']], parsed[['Outside', 'Water', 'Inlet']])
                if not legacy:
                    with fitz.open(stream=output, filetype='pdf') as exported:
                        exported[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save('/tmp/kleventa-test.png')


if __name__ == '__main__':
    unittest.main()
