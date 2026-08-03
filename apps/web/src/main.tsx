import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import "antd/dist/reset.css";
import "@xyflow/react/dist/style.css";
import "./styles.css";
import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 1_000 },
    mutations: { retry: 0 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: "#002fa7",
            colorInfo: "#002fa7",
            colorSuccess: "#16865c",
            colorWarning: "#c97800",
            colorError: "#c53b3f",
            colorText: "#172033",
            colorTextSecondary: "#657084",
            colorBorder: "#d9dde5",
            colorBgLayout: "#f4f6f9",
            borderRadius: 6,
            fontSize: 12,
            controlHeight: 34,
          },
          components: {
            Button: { primaryShadow: "none", borderRadius: 5 },
            Drawer: { borderRadiusLG: 0 },
            Menu: { itemBorderRadius: 4, itemHeight: 40, itemMarginBlock: 3 },
            Table: { headerBg: "#f4f6f9", headerColor: "#657084", rowHoverBg: "#f2f6ff" },
          },
        }}
      >
        <AntApp><App /></AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  </StrictMode>,
);
