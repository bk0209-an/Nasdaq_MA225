"""
매일 아침 알림용 MA225 신호 — 오늘 국내장에서 할 행동 한 가지를 출력.

    어제 상태 → 오늘 상태     행동
    2배      → 2배           2배 보유
    2배      → 1배           2배 매도 후, 1배 매수
    1배      → 1배           1배 보유
    1배      → 2배           1배 매도 후, 2배 매수

신호: QQQ 수정종가 vs 225일 단순이동평균 (signal_now.py / 백테스트와 동일).
미국 d 일 종가로 판정 → 국내 d 다음 거래일에 체결.

파이썬 표준 라이브러리만 사용 (pip 설치 불필요) — GitHub bk0209-an/Nasdaq_MA225 의
클라우드 루틴이 패키지 저장소 접속 없이 실행할 수 있도록. 야후 차트 API 를 직접 호출한다.
캐시를 쓰지 않으므로 data/raw 를 건드리지 않는다.

첫 줄은 푸시 알림 본문용 한 줄 요약 (200자 이내).
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

MA = 225
PRODUCT_2X = "TIGER 미국나스닥100레버리지(합성) 418660"
PRODUCT_1X = "TIGER 미국나스닥100 133690"
STALE_DAYS = 4          # 마지막 미국 거래일이 이보다 오래되면 데이터 지연 경고
TREND_DAYS = 21         # 알림 미니 차트 = 최근 1개월(거래일 21일)
SPARK = "▁▂▃▄▅▆▇█"
KST = timezone(timedelta(hours=9))
URLS = [f"https://{host}/v8/finance/chart/QQQ?range=2y&interval=1d&events=div%2Csplit"
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com")]

ACTIONS = {
    (True, True): "2배 보유",
    (True, False): "2배 매도 후, 1배 매수",
    (False, False): "1배 보유",
    (False, True): "1배 매도 후, 2배 매수",
}


def download_qqq() -> list[tuple[date, float]]:
    """QQQ 일별 수정종가 [(미국 거래일, 가격)]. MA225 에 충분한 2년치."""
    last_err: Exception | None = None
    for attempt in range(1, 5):
        for url in URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    res = json.load(resp)["chart"]["result"][0]
                tz = timezone(timedelta(seconds=res["meta"]["gmtoffset"]))
                adj = res["indicators"]["adjclose"][0]["adjclose"]
                rows = [(datetime.fromtimestamp(t, tz).date(), float(p))
                        for t, p in zip(res["timestamp"], adj) if p is not None]
                if len(rows) > MA + 1:
                    return rows
                last_err = RuntimeError(f"데이터 부족 ({len(rows)}행)")
            except Exception as exc:  # noqa: BLE001 - 재시도 목적
                last_err = exc
        time.sleep(2 * attempt)
    raise RuntimeError(f"QQQ 다운로드 실패: {last_err}")


def sparkline(values: list[float]) -> str:
    """값 목록을 ▁▂▃▄▅▆▇█ 8단계 글자 차트로 (푸시 알림은 텍스트만 가능)."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARK[3] * len(values)
    return "".join(SPARK[round((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in values)


def main() -> None:
    rows = download_qqq()
    dates = [d for d, _ in rows]
    px = [p for _, p in rows]
    ma = [sum(px[i - MA + 1:i + 1]) / MA if i >= MA - 1 else None for i in range(len(px))]
    up = [m is not None and p >= m for p, m in zip(px, ma)]

    d, d_prev = dates[-1], dates[-2]
    p_now, m = px[-1], ma[-1]
    prev_up, now_up = up[-2], up[-1]
    action = ACTIONS[(prev_up, now_up)]
    switch = prev_up != now_up
    gap = p_now / m - 1

    age = (datetime.now(KST).date() - d).days
    stale = f" ⚠️미국 데이터 {age}일 지연" if age > STALE_DAYS else ""
    flag = "🔔전환" if switch else "✅유지"

    # 최근 1개월 추세: MA225 이격도(종가/MA − 1) 미니 차트 + 시작→현재 이격도.
    # 차트는 1개월 구간의 최저~최고로 그린 상대 모양이라 0%(전환선) 위치는 나타나지 않는다.
    k = -TREND_DAYS - 1                      # 21거래일 전을 기준점으로
    gaps = [p / mm - 1 for p, mm in zip(px[k:], ma[k:])]
    trend = f"이격 1개월 {sparkline(gaps)} {gaps[0]:+.1%}→{gap:+.1%}"

    # 1줄 요약 (푸시 본문, 200자 이내)
    print(f"{flag} {action} | QQQ {p_now:,.2f} vs MA225 {m:,.2f} ({gap:+.2%}) "
          f"[미국 {d:%m/%d} 종가]{stale} | {trend}")

    # 상세
    i = len(up) - 1
    while i > 0 and up[i - 1] == now_up:
        i -= 1
    since = dates[i]
    hold = PRODUCT_2X if now_up else PRODUCT_1X
    print()
    print(f"판정 기준일    : 미국 {d} 종가 (전일 {d_prev}: {'2배' if prev_up else '1배'})")
    print(f"오늘 국내장    : {action}")
    if switch:
        sell, buy = (PRODUCT_2X, PRODUCT_1X) if prev_up else (PRODUCT_1X, PRODUCT_2X)
        print(f"  매도 → {sell} 전량")
        print(f"  매수 → {buy} (매도 대금 전액)")
    print(f"보유 상품      : {hold}  (미국 {since} 신호부터)")
    print(f"월 납입금      : {hold} 매수")
    print(f"전환 임계가    : QQQ {m:,.2f}  (현재가에서 {m / p_now - 1:+.2%})")


if __name__ == "__main__":
    main()
