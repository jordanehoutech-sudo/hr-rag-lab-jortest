import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const deploymentBuild = command === "build" &&
    (env.VITE_AUTH_MODE === "cognito" || Boolean(process.env.HR_STAGING_FRONTEND_BUCKET));

  // Login settings are compiled into React. Stop a deployment build if they are absent.
  if (deploymentBuild) {
    const required = ["VITE_COGNITO_AUTHORITY", "VITE_COGNITO_CLIENT_ID", "VITE_COGNITO_DOMAIN"];
    const missing = required.filter((name) => !env[name]?.trim());
    if (missing.length) throw new Error(`Missing Cognito build settings: ${missing.join(", ")}`);
    for (const name of ["VITE_COGNITO_AUTHORITY", "VITE_COGNITO_DOMAIN"]) {
      if (new URL(env[name]).protocol !== "https:") throw new Error(`${name} must use HTTPS`);
    }
  }

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: process.env.API_URL ? { "/api": process.env.API_URL } : undefined,
    },
  };
});
