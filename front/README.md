# 사용자 대시보드

React + Vite 기반의 사용자 대시보드 UI입니다.

원본 시각 디자인은 다음 Figma 파일을 기반으로 했습니다.
`https://www.figma.com/design/7YTrVb4SSEYxhdOtgiFq6C/User-dashboard`

## 권장 디렉터리 구조

```text
src/
  app/         # 앱 시작점 및 부트스트랩
  features/    # 화면 단위 기능 모듈
  layouts/     # 공통 레이아웃
  routes/      # 라우터 설정
  shared/      # 재사용 가능한 UI 및 공용 유틸
  styles/      # 전역 스타일 및 테마 파일
```

## 실행 방법

### 1. 프론트엔드 디렉터리로 이동

```bash
cd front
```

### 2. 의존성 설치

```bash
npm install
```

`package.json`에 정의된 라이브러리를 처음 한 번 설치하는 단계입니다.

### 3. 개발 서버 실행

```bash
npm run dev
```

실행이 완료되면 터미널에 로컬 접속 주소가 표시됩니다.
보통 `http://localhost:5173` 형태의 주소로 접속할 수 있습니다.

## 참고

- 개발 중 코드를 수정하면 Vite의 HMR 기능으로 화면이 자동 갱신됩니다.
- `node_modules`가 없거나 의존성이 바뀌었다면 `npm install`을 다시 실행하세요.
