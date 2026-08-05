import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

export function configureApiBaseUrl(apiBaseUrl?: string): void {
  api.defaults.baseURL = apiBaseUrl
    ? `${apiBaseUrl.replace(/\/$/, "")}/api`
    : "/api";
}

export default api;
