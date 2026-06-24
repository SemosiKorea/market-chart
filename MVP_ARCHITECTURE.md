# 시장 신호 비교 MVP 아키텍처

## 흐름

IBKR 지연 NQ/MNQ 공급자와 KIS QQQ 주간거래 공급자가 독립적으로 데이터를 수신한다. 각 원본 응답은 공통 `MarketQuote` 모델로 변환하고 SQLite에 저장한다. 이후 시장시각 기준 비교와 실제 수신시각 기준 비교를 별도로 수행한다.

## 모듈

- `providers`: IBKR와 KIS 연결
- `domain`: 공통 데이터 모델
- `normalization`: 시간, 가격, 수익률, 호가 품질
- `storage`: SQLite 저장과 조회
- `comparison`: 시각 정렬과 통계
- `signals`: 연구용 임계값 이벤트
- `reporting`: 결과 출력

실제 폴더 위치는 기존 저장소 구조 조사 후 정한다.

## MarketQuote 필드

- source
- instrument_type
- symbol
- session
- market_timestamp
- received_at
- last_price
- bid_price
- ask_price
- bid_size
- ask_size
- reference_price
- data_delay_type
- quality_status

내부 시간은 UTC aware datetime으로 저장하고, 화면에서만 Asia/Seoul로 변환한다.

## QQQ 품질 규칙

유효한 bid와 ask가 있으면 중간값을 사용한다. 유효 호가가 없고 최신 체결이 있으면 마지막 체결가를 사용한다. 둘 다 유효하지 않으면 비교에서 제외한다.

초기 설정값:

- 최대 호가 경과시간 30초
- 최대 스프레드 0.30%
- bid와 ask는 0보다 커야 함
- ask는 bid 이상이어야 함

이 값은 데이터 품질 검증용 초기값이며 투자 기준이 아니다.

## 비교 방식

- 시장시각 기준: 같은 시장 시점의 QQQ와 지연 선물을 비교
- 수신시각 기준: 프로그램이 실제로 받은 시점 기준으로 비교

두 결과는 혼합하지 않고 별도 통계로 저장한다.

## 저장 대상

- 정규화된 가격과 호가
- 공급자 연결 상태
- 연구용 신호 이벤트
- 기간별 비교 통계

## 장애 및 보안

한 공급자의 장애가 다른 공급자를 중단시키지 않아야 한다. 오래된 데이터로 새 신호를 만들지 않는다. 자격증명은 환경변수에서만 읽고 로그에 토큰이나 계좌번호를 남기지 않는다. 실제 주문 기능은 1차 MVP에 포함하지 않는다.
