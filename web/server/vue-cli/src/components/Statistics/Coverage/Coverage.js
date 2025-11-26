import Vue from "vue";

import CoverageLine from "./CoverageLine";
const CoverageLineClass = Vue.extend(CoverageLine);

function getCoverageColor(status) {
  switch (status) {
  case "covered":
    return "rgb(200, 255, 200)"; // Light green
  case "uncovered":
    return "rgb(255, 200, 200)"; // Light red
  case "not_executed":
    return "rgb(240, 240, 240)"; // Light gray
  default:
    return "rgb(255, 255, 255)"; // White
  }
}

function getCoverageData(filePath, coverageMap) {
  // coverageMap format: { "file.c": [1, 2, 3, ...] } - covered lines
  // Match the file path (can be full path or just filename)
  let coveredLines = [];
  let matchedKey = null;

  if (coverageMap && filePath) {
    // Try exact match first
    if (coverageMap[filePath]) {
      matchedKey = filePath;
      coveredLines = coverageMap[filePath];
    } else {
      // Try to find by filename
      const fileName = filePath.split("/").pop();
      matchedKey = Object.keys(coverageMap).find(key =>
        key === fileName || key.endsWith(fileName));
      if (matchedKey) {
        coveredLines = coverageMap[matchedKey];
      }
    }
  }

  return {
    fileName: matchedKey || filePath,
    coveredLines: new Set(coveredLines),
    coverage: {}
  };
}

function getCoverageInfo(filePath, coverageMap) {
  // In a real implementation, this would fetch from API
  // For now, we'll use the coverageMap passed in
  return new Promise(res => {
    // Simulate API call - replace with actual API call when available
    setTimeout(() => {
      const data = getCoverageData(filePath, coverageMap);
      res(data);
    }, 0);
  });
}

export default {
  data() {
    return {
      editor: null,
      gutterID: "coverage-gutter",
      gutterMarkers: {},
      coverageData: null,
      sourceFile: null,
      coverageMap: null, // This will hold the coverage JSON data
    };
  },
  methods: {
    hideCoverageView() {
      return new Promise(res => {
        if (!this.editor) {
          res();
          return;
        }

        this.resetCoverageView();

        this.editor.clearGutter(this.gutterID);
        this.editor.setOption("gutters", []);
        this.editor.setOption("lineNumbers", true);

        this.$nextTick(() => {
          this.editor.refresh();

          this.$router.replace({
            query: {
              ...this.$route.query,
              "view": undefined
            }
          }).catch(() => {});
          res();
        });
      });
    },

    resetCoverageView() {
      if (this.editor) {
        this.editor.off("viewportChange", this.onViewportChange);
      }
      this.gutterMarkers = {};
    },

    setGutterMarker(from, to) {
      if (!this.editor || !this.coverageData ||
          !this.coverageData.coveredLines) {
        return;
      }

      this.editor.operation(() => {
        for (let i = from; i < to; ++i) {
          const lineNum = i + 1;
          const isCovered = this.coverageData.coveredLines.has(lineNum);

          // If the marker already exists we can skip adding it again.
          if (this.gutterMarkers[i])
            continue;

          const status = isCovered ? "covered" : "uncovered";
          const color = getCoverageColor(status);

          const widget = new CoverageLineClass({
            propsData: {
              number: lineNum,
              status: status,
              color: color
            }
          });

          // This is needed otherwise it will throw an error.
          widget.$vuetify = this.$vuetify;

          widget.$mount();

          this.editor.setGutterMarker(i, this.gutterID, widget.$el);
          this.gutterMarkers[i] = true;
        }
      });

      this.$nextTick(() => this.editor.refresh());
    },

    onViewportChange(cm, from, to) {
      this.setGutterMarker(from, to);
    },

    async loadCoverageView(coverageMap) {
      if (!this.sourceFile || !coverageMap || !this.editor) {
        return;
      }

      this.coverageMap = coverageMap;
      // Use filePath instead of fileId for matching
      this.coverageData = await getCoverageInfo(
        this.sourceFile.filePath, coverageMap);

      if (!this.coverageData) {
        return;
      }

      this.resetCoverageView();
      this.editor.setOption("gutters", [ this.gutterID ]);
      this.editor.setOption("lineNumbers", false);

      // Initialize the gutter markers.
      const { from, to } = this.editor.getViewport();
      this.setGutterMarker(from, to);

      // Add gutter markers on viewport change event.
      this.editor.on("viewportChange", this.onViewportChange);

      this.$router.replace({
        query: {
          ...this.$route.query,
          "view": "coverage"
        }
      }).catch(() => {});
    }
  }
};

