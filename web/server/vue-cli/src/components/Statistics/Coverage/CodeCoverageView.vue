<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            Code Coverage View
          </v-card-title>

          <v-card-text>
            <v-row>
              <v-col cols="12" md="6">
                <v-select
                  v-model="selectedFile"
                  :items="fileList"
                  :loading="loading"
                  label="Select file from coverage"
                  item-text="name"
                  item-value="fileId"
                  return-object
                  @change="loadFile"
                >
                  <template v-slot:item="{ item }">
                    <v-list-item-content>
                      <v-list-item-title>
                        {{ item.name }}
                      </v-list-item-title>
                      <v-list-item-subtitle>
                        {{ item.path }}
                      </v-list-item-subtitle>
                    </v-list-item-content>
                  </template>
                </v-select>
              </v-col>
            </v-row>

            <v-row
              v-if="sourceFile"
              v-fill-height
              class="editor ma-0"
              style="min-height: 500px;"
            >
              <v-col cols="12">
                <v-progress-linear
                  v-if="loading"
                  indeterminate
                  class="mb-2"
                />
                <textarea ref="editor" style="display: none;" />
              </v-col>
            </v-row>

            <v-alert
              v-else-if="!loading"
              type="info"
              class="mt-4"
            >
              Please select a file to view coverage information.
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
import CodeMirror from "codemirror";
import "codemirror/lib/codemirror.css";
import "codemirror/mode/clike/clike.js";

import { FillHeight } from "@/directives";
import { ccService, handleThriftError } from "@cc-api";
import { Encoding } from "@cc/report-server-types";

export default {
  name: "CodeCoverageView",
  components: {},
  directives: { FillHeight },
  data() {
    return {
      editor: null,
      sourceFile: null,
      selectedFile: null,
      fileList: [],
      coveredLines: [],
      loading: false
    };
  },
  mounted() {
    this.loadFileList();
  },
  methods: {
    async loadFileList() {
      this.loading = true;
      try {
        const client = ccService.getClient();

        // Check if the function exists (Thrift API might not be
        // regenerated yet)
        if (typeof client.getFilesWithCoverage !== "function") {
          this.fileList = [];
          this.loading = false;
          return;
        }

        const files = await new Promise((resolve, reject) => {
          client.getFilesWithCoverage(
            handleThriftError(
              result => resolve(result),
              error => reject(error)
            )
          );
        });

        this.fileList = files.map(file => ({
          fileId: file.fileId,
          name: file.filePath.split("/").pop() || file.filePath,
          path: file.filePath
        }));
      } catch (error) {
        // Handle Thrift read errors gracefully
        if (error && error.message && error.message.includes("read")) {
          // Thrift API not regenerated - function doesn't exist
          this.fileList = [];
        } else {
          this.fileList = [];
        }
      } finally {
        this.loading = false;
      }
    },

    async loadFile(file) {
      if (!file || !file.fileId) {
        return;
      }

      this.loading = true;
      try {
        const fileId = file.fileId;


        const [ sourceFile, coveredLines ] = await Promise.all([
          new Promise((resolve, reject) => {
            ccService.getClient().getSourceFileData(
              fileId,
              true,
              Encoding.DEFAULT,
              handleThriftError(
                result => resolve(result),
                error => reject(error)
              )
            );
          }),
          new Promise((resolve, reject) => {
            ccService.getClient().getTestCoverage(
              fileId,
              handleThriftError(
                result => resolve(result),
                error => reject(error)
              )
            );
          })
        ]);

        this.sourceFile = sourceFile;
        this.coveredLines = coveredLines.map(
          line => parseInt(line, 10)
        );

        // Initialize editor if not already initialized
        await this.$nextTick();
        if (!this.editor && this.$refs.editor) {
          this.editor = CodeMirror.fromTextArea(this.$refs.editor, {
            lineNumbers: true,
            readOnly: true,
            mode: "text/x-c++src",
            gutters: [ "CodeMirror-linenumbers" ],
            viewportMargin: 200
          });
          this.editor.setSize("100%", "100%");
        }

        if (this.editor) {
          this.editor.setValue(sourceFile.fileContent || "");
        }

        // Apply coverage highlights
        await this.applyCoverageHighlights();
      } catch (error) {
        // Error loading file
      } finally {
        this.loading = false;
      }
    },


    async applyCoverageHighlights() {
      if (!this.editor || !this.sourceFile || !this.coveredLines) {
        return;
      }

      // Clear existing highlights
      this.clearCoverageHighlights();

      if (this.coveredLines.length === 0) {
        return;
      }

      const coveredSet = new Set(this.coveredLines);
      const totalLines = this.editor.lineCount();

      // Apply line highlights
      this.editor.operation(() => {
        for (let i = 0; i < totalLines; i++) {
          const lineNum = i + 1;
          const isCovered = coveredSet.has(lineNum);

          // Add CSS class to highlight the entire line
          this.editor.addLineClass(i, "background",
            isCovered ? "coverage-line-covered" :
              "coverage-line-uncovered");
        }
      });

      this.editor.refresh();
    },

    clearCoverageHighlights() {
      if (!this.editor) {
        return;
      }

      // Remove CSS classes from all lines
      const totalLines = this.editor.lineCount();
      this.editor.operation(() => {
        for (let i = 0; i < totalLines; i++) {
          this.editor.removeLineClass(i, "background",
            "coverage-line-covered");
          this.editor.removeLineClass(i, "background",
            "coverage-line-uncovered");
        }
      });
    }
  }
};
</script>

<style lang="scss" scoped>
.editor {
  font-size: initial;
  line-height: initial;

  ::v-deep .CodeMirror-code > div:hover {
    background-color: lighten(grey, 42%);
  }
}

::v-deep .coverage-line-covered {
  background-color: rgba(200, 255, 200, 0.5) !important;
}

::v-deep .coverage-line-uncovered {
  background-color: rgba(255, 200, 200, 0.5) !important;
}
</style>

