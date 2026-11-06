import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datafile  # noqa: E402


class DataFileTests(unittest.TestCase):
    def payload(self):
        return datafile.build_payload("Sphere", {"SphereDiameterLineEdit": "10", "checkBox_x": True, "SphereGasTypeComboBox": "氦气"},
                                      {"aux_ratio_manual": True}, {"工作风结论": "合格"}, {"project": "测试"})

    def test_round_trip_keeps_chinese_and_types(self):
        loaded = datafile.loads(datafile.dumps(self.payload()))
        self.assertEqual(loaded["kind"], "Sphere")
        self.assertEqual(loaded["inputs"]["SphereDiameterLineEdit"], "10")
        self.assertIs(loaded["inputs"]["checkBox_x"], True)
        self.assertEqual(loaded["inputs"]["SphereGasTypeComboBox"], "氦气")
        self.assertTrue(loaded["state"]["aux_ratio_manual"])
        self.assertEqual(loaded["report_info"]["project"], "测试")

    def test_file_is_plain_readable_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a.txt")
            datafile.write_file(path, self.payload())
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("氦气", text)
            self.assertEqual(datafile.read_file(path)["inputs"], self.payload()["inputs"])

    def test_reads_utf8_bom_and_gbk(self):
        text = datafile.dumps(self.payload())
        with tempfile.TemporaryDirectory() as folder:
            for name, raw in (("bom.txt", b"\xef\xbb\xbf" + text.encode("utf-8")), ("gbk.txt", text.encode("gb18030"))):
                path = os.path.join(folder, name)
                with open(path, "wb") as handle:
                    handle.write(raw)
                self.assertEqual(datafile.read_file(path)["kind"], "Sphere")

    def test_rejects_bad_files_with_clear_messages(self):
        for text, fragment in (("not json", "不是有效"), ("[1, 2]", "不是本程序"), ('{"format": "Other"}', "不是本程序"),
                               ('{"format": "AerostatDesignData", "version": 99, "kind": "Sphere", "inputs": {}}', "升级"),
                               ('{"format": "AerostatDesignData", "version": 1, "kind": "Ship", "inputs": {}}', "类型"),
                               ('{"format": "AerostatDesignData", "version": 1, "kind": "Sphere"}', "缺少输入"),
                               ('{"format": "AerostatDesignData", "version": 1, "kind": "Sphere", "inputs": {"a": 3}}', "类型不合法")):
            with self.assertRaises(datafile.DataFileError) as caught:
                datafile.loads(text)
            self.assertIn(fragment, str(caught.exception))

    def test_unknown_kind_cannot_be_built(self):
        with self.assertRaises(datafile.DataFileError):
            datafile.build_payload("Balloon", {})


if __name__ == "__main__":
    unittest.main()
