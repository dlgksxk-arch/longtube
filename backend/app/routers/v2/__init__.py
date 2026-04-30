"""v2.x 신규 라우터 묶음.

구 라우터(``app/routers/*.py``) 와 **병렬**로 존재한다. v2.4.0 이전까지
구 라우터는 전혀 건드리지 않는다.

URL prefix 규약: 각 서브모듈은 ``router`` 변수를 노출하고,
``main.py`` 에서 ``/api/v2/<name>`` prefix 로 include 한다.
"""
