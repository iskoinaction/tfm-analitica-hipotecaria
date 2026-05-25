from app import app, demanda_data
with app.test_request_context('/api/demanda-data'):
    res = demanda_data()
    print("STATUS:", res.status_code)
    print("DATA OK:", b'benchmark' in res.data)
