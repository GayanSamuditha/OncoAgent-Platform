import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [{ ignores: ["playwright-report/**", "test-results/**"] }, ...nextVitals];

export default eslintConfig;
