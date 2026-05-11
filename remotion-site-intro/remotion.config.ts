import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
/** 与后端默认 8000 错开，便于同时开 FastAPI 与本 Studio */
Config.setStudioPort(3333);
