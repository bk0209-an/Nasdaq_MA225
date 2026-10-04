"""
매일 아침 알림용 MA225 신호 — 오늘 국내장에서 할 행동 한 가지를 출력.

    어제 상태 → 오늘 상태     행동
    2배      → 2배           2배 보유
    2배      → 1배           2배 매도 후, 1배 매수
    1배      → 1배           1배 보유
    1배      → 2배           1배 매도 후, 2배 매수

신호: QQQ 수정종가 vs 225일 단순이동평균 (signal_now.py / 백테스트와 동일).
미국 d 일 종가로 판정 → 국내 d 다음 거래일에 체결.

단독 실행 파일 (pandas, yfinance 만 필요) — GitHub bk0209-an/Nasdaq_MA225 의 클라우드
루틴에서도 같은 파일을 쓴다. 캐시를 쓰지 않으므로 data/raw 를 건드리지 않는다.

첫 줄은 푸시 알림 본문용 한 줄 요약 (200자 이내).
"""
from __future__ import annotations

import time

import pandas as pd

MA = 225
PRODUCT_2X = "TIGER 미국나스닥100레버리지(합성) 418660"
PRODUCT_1X = "TIGER 미국나스닥100 133690"
STALE_DAYS = 4          # 마지막 미국 거래일이 이보다 오래되면 데이터 지연 경고

ACTIONS = {
    (True, True): "2배 보유",
    (True, False): "2배 매도 후, 1배 매수",
    (False, False): "1배 보유",
    (False, True): "1배 매도 후, 2배 매수",
}


def download_qqq() -> pd.Series:
    """QQQ 수정종가. MA225 에 충분한 2년치만 받는다 (전체 이력 MA 와 결과 동일)."""
    import yfinance as yf

    last_err: Exception | None = None
    for attempt in range(1, 5):
        try:
            df = yf.download("QQQ", period="2y", auto_adjust=True, progress=False,
                             actions=False, threads=False)
            if df is not None and not df.empty:
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
                close = close.dropna()
                close.index = pd.to_datetime(close.index).tz_localize(None)
                return close.astype(float)
            last_err = RuntimeError("empty frame")
        except Exception as exc:  # noqa: BLE001 - 재시도 목적
            last_err = exc
        time.sleep(2 * attempt)
    raise RuntimeError(f"QQQ 다운로드 실패: {last_err}")


def main() -> None:
    qqq = download_qqq()
    ma = qqq.rolling(MA).mean()
    up = qqq >= ma

    d, d_prev = qqq.index[-1], qqq.index[-2]
    px, m = float(qqq.iloc[-1]), float(ma.iloc[-1])
    prev_up, now_up = bool(up.iloc[-2]), bool(up.iloc[-1])
    action = ACTIONS[(prev_up, now_up)]
    switch = prev_up != now_up
    gap = px / m - 1

    now_kst = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()
    age = (now_kst - d).days
    stale = f" ⚠️미국 데이터 {age}일 지연" if age > STALE_DAYS else ""
    flag = "🔔전환" if switch else "✅유지"

    # 1줄 요약 (푸시 본문)
    print(f"{flag} {action} | QQQ {px:,.2f} vs MA225 {m:,.2f} ({gap:+.2%}) "
          f"[미국 {d:%m/%d} 종가]{stale}")

    # 상세
    flips = up.ne(up.shift()).cumsum()
    since = up[flips == flips.iloc[-1]].index[0]
    hold = PRODUCT_2X if now_up else PRODUCT_1X
    print()
    print(f"판정 기준일    : 미국 {d.date()} 종가 (전일 {d_prev.date()}: "
          f"{'2배' if prev_up else '1배'})")
    print(f"오늘 국내장    : {action}")
    if switch:
        sell, buy = (PRODUCT_2X, PRODUCT_1X) if prev_up else (PRODUCT_1X, PRODUCT_2X)
        print(f"  매도 → {sell} 전량")
        print(f"  매수 → {buy} (매도 대금 전액)")
    print(f"보유 상품      : {hold}  (미국 {since.date()} 신호부터)")
    print(f"월 납입금      : {hold} 매수")
    print(f"전환 임계가    : QQQ {m:,.2f}  (현재가에서 {m / px - 1:+.2%})")


if __name__ == "__main__":
    main()
