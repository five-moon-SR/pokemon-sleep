from __future__ import annotations

import unittest

from scripts.fetch_field_encounters import parse_encounters


class FetchFieldEncountersTest(unittest.TestCase):
    def test_parse_uses_rating_table_not_master_like_table(self) -> None:
        html = """
        <table>
          <tr><th>No.</th><th>名前</th><th>睡眠</th><th>得意</th><th>木実</th></tr>
          <tr><td>0149</td><td>カイリュー</td><td>うとうと</td><td>食材</td><td>ヤチェのみ</td></tr>
        </table>
        <h3>各カビゴン評価の詳細</h3>
        <table>
          <tr><td>スクロール可</td><th colspan="2">エナジー</th><th>ゆめのかけら</th><th colspan="3">出会えるようになるポケモン</th></tr>
          <tr><th>評価</th><th>必要</th><th>総</th><th>報酬</th><th>うとうと</th><th>すやすや</th><th>ぐっすり</th></tr>
          <tr>
            <td>1</td><td>0</td><td>-</td><td>0</td>
            <td>-</td>
            <td>-</td>
            <td><a href="/poke_sleep/%E3%83%A8%E3%83%BC%E3%82%AE%E3%83%A9%E3%82%B9" title="ヨーギラス" class="rel-wiki-page">ヨーギラス</a></td>
          </tr>
        </table>
        """
        names = [r["species_name"] for r in parse_encounters(html, {"カイリュー", "ヨーギラス"})]
        self.assertEqual(names, ["ヨーギラス"])


if __name__ == "__main__":
    unittest.main()
