import json
import sqlite3
from external_watch.delivery import DeliveryStore
from external_watch.calibration import calibration_report


def test_calibration_suggests_but_never_mutates_profile(tmp_path):
    db=tmp_path/"x.db"; store=DeliveryStore(db)
    for i in range(3):
        c={"source":"calendar","item_key":str(i),"change_type":"new","payload":{},"relevance":{"categories":["career"]}}
        key=f"k{i}"; store.record_delivery(key,c,None); store.record_feedback(key,"noise")
    report=calibration_report(db)
    assert report["profile_mutated"] is False
    assert {x["kind"] for x in report["suggestions"]} >= {"source_downrank","category_downweight"}
