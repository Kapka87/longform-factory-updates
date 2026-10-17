# EN_BTS Discovery Gate — 사용자가 해야 할 단계

준비된 GitHub PR이 main에 반영되면 다음 단계로 라이브 검증을 완료할 수 있다.

1. Google Cloud Console(https://console.cloud.google.com/) 로그인 → 프로젝트 선택/생성 → YouTube Data API v3 사용 설정(https://console.cloud.google.com/apis/library/youtube.googleapis.com).
2. **APIs & Services → Credentials → Create Credentials → API key**. API restrictions에서 **YouTube Data API v3**만 허용. 키 문자열은 채팅/코드에 입력하지 않는다. 할당량/사용량을 확인한다. 공용 GitHub runner IP는 고정되지 않으므로 특정 고정 IP 제한 설정 시 실행 실패할 수 있다.
3. GitHub `Kapka87/longform-factory-updates` → Settings → Secrets and variables → Actions → New repository secret → Name `YOUTUBE_API_KEY` → Value에 키를 붙여넣고 저장.
4. 검수된 Pull Request를 **Merge**하여 workflow가 main에 존재하도록 한다. (GitHub `workflow_dispatch`는 기본 브랜치에 등록되어야 수동 실행 버튼이 보인다.)
5. Actions → `EN BTS Discovery Gate - manual official collection` → Run workflow → branch `main` → Run workflow.
6. 성공 후 해당 run의 Artifacts에서 `en-bts-discovery-v1-...` 내려받기 → `report.md` 확인. `LIVE_API`인지, 자료 누락이 없는지 확인. 문제가 있으면 실행 로그의 오류 문구만 전달하고 키는 전달하지 않는다.

**비용:** Python 패키지 설치 0개. 일반 기본 API 할당량 안에서 호출하도록 26회 검색 예산으로 제한. 하지만 Google Cloud의 유료 결제/프로젝트 정책은 사용자 계정별로 다를 수 있으므로 Cloud Console에서 과금 상태 확인 권장. GitHub Actions 실행/저장 비용 역시 사용 중 요금제·공개/비공개 저장소에 따라 달라짐.

**제작:** 자동 대본/영상 생성 없음. 수집 코드만 실행.