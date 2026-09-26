# job-radar-data — 채용 레이더 원천 데이터 수집기

채용 레이더(https://claude.ai/artifact/UEptXqaUbSow3eXfvDHh1t)의 클라우드 일일 작업이 읽을 원천 데이터를 GitHub Actions가 매일 06:10 KST에 공식 API로 모아 `data/`에 커밋한다. 클라우드 작업은 이 저장소를 clone해서 `data/summary.md`와 `data/latest.json`을 읽는다(WebFetch 요약을 거치지 않으므로 마감일·URL·지원자 수가 유실되지 않는다).

수집원은 모두 공식·공개 API다. robots나 약관으로 막힌 사이트(원티드, 잡플래닛, 자소설닷컴, 잡다, 링크드인, recruiter.co.kr)는 여기서 다루지 않는다.

| 스크립트 | 원천 | 키 | 주기 | 얻는 것 |
|---|---|---|---|---|
| collect/saramin.py | 사람인 오픈 API | SARAMIN_KEY (무료) | 매일 | 검색어별 최신 공고: 회사, 제목, 직무, 경력, 학력, 고용형태, 지역, 마감일, URL, 지원자 수·조회수 |
| collect/ats.py | Greenhouse·Lever 공개 Job Board API | 없음 | 매일 | 해외·외국계 회사의 Graduate/Intern/Associate 공고 원문 |
| collect/dart.py | 금감원 DART 오픈API 직원현황 | DART_KEY (무료) | 주 1회 | 공시 법인의 직원 수, 1인 평균 급여, 평균 근속 |
| collect/nps.py | 공공데이터포털 국민연금 가입 사업장 | DATA_GO_KR_KEY (무료) | 주 1회 | 비상장 포함 사업장 가입자 수, 고지액 기반 추정 연봉 |

## 설정 (한 번만)

1. GitHub에 비공개 저장소를 만들고 이 폴더 내용을 그대로 push한다.
2. API 키 발급(모두 무료, 가입 후 즉시 또는 1~2일 내):
   - 사람인 오픈 API: https://oapi.saramin.co.kr → 앱 등록 → access-key. 일일 요청 한도가 있으므로 `config/keywords.json`의 검색어 수(기본 22개)를 그 안에서 조정한다.
   - DART: https://opendart.fss.or.kr → 인증키 신청(일 20,000건 한도).
   - 공공데이터포털: https://www.data.go.kr 에서 "국민연금공단_국민연금 가입 사업장 내역" 활용 신청 → 일반 인증키(Decoding 값 사용).
3. 저장소 Settings → Secrets and variables → Actions에 `SARAMIN_KEY`, `DART_KEY`, `DATA_GO_KR_KEY`를 등록한다. 키가 없는 수집기는 그 단계만 건너뛴다.
4. Actions 탭에서 `collect-job-data`를 "Run workflow"로 한 번 수동 실행해 `data/summary.md`가 생기는지 확인한다.
5. 채용 레이더 운영 프로토콜(프로젝트 문서 14) §5의 0단계에 이 저장소 주소를 적는다. 비공개 저장소면 클라우드 작업이 clone할 수 있도록 read-only Fine-grained token을 발급해 프로토콜에 함께 적거나, 저장소를 public으로 둔다(공고 메타데이터만 있어 민감 정보는 없음).

## 유지보수

- 검색어 추가·제외 패턴: `config/keywords.json`
- 해외 회사 추가: 회사 채용 페이지 URL이 `boards.greenhouse.io/<board>` 또는 `jobs.lever.co/<site>` 형태면 `config/ats_boards.json`에 넣는다. Workday·SuccessFactors·SmartRecruiters는 공식 공개 API가 아니거나 robots로 막혀 있어 넣지 않는다.
- 기업 데이터 대상: `config/companies.json`. DART는 corpCode의 법인명, 국민연금은 사업장명과 부분 일치해야 잡힌다. 잘못 매칭되면 `data/companies.json`의 `corp_name`/`wkplNm`을 보고 이름을 고친다.
- 국민연금 추정 연봉은 고지액/가입자수/보험료율(2026년 9.5%, 매년 7월 상한 갱신)로 계산하므로 고연봉 기업은 기준소득월액 상한 때문에 과소 추정된다. `ceiling_hit`가 true면 DART 값을 우선한다.

## 알려진 제한

- 사람인 API는 공고 본문을 주지 않는다. 요건(졸업예정자 가능, 언어, 입사일)은 여전히 URL을 열어 확인해야 한다. 이 저장소는 "무엇을 열어볼지"를 정확한 마감일·지원자 수와 함께 주는 역할이다.
- 잡코리아·링커리어·인크루트는 공개 API가 없어 기존처럼 클라우드 작업이 페이지를 직접 읽는다.
- 잡플래닛 평점·추천율, 자소설닷컴 경쟁률·합격후기는 대체 공개 소스가 없다. PC 로그인 작업이 계속 담당한다.
