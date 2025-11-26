<template>
  <div
    :class="[
      'coverage-line',
      status ? 'coverage-line-full' : undefined
    ]"
  >
    <span
      class="coverage-status"
      :title="statusText"
    >
      <v-icon
        v-if="status === 'covered'"
        small
        color="green"
      >
        mdi-check-circle
      </v-icon>
      <v-icon
        v-else-if="status === 'uncovered'"
        small
        color="red"
      >
        mdi-close-circle
      </v-icon>
      <v-icon
        v-else
        small
        color="grey"
      >
        mdi-circle-outline
      </v-icon>
    </span>

    <span
      class="coverage-line-number"
      :style="{'background-color': color }"
    >
      {{ number }}
    </span>
  </div>
</template>

<script>
export default {
  name: "CoverageLine",
  props: {
    status: { type: String, default: "not_executed" },
    number: { type: Number, required: true },
    color: { type: String, required: true }
  },
  computed: {
    statusText() {
      switch (this.status) {
      case "covered":
        return "Line is covered";
      case "uncovered":
        return "Line is not covered";
      default:
        return "Line was not executed";
      }
    }
  }
};
</script>

<style lang="scss" scoped>
.coverage-line-full {
  border-top: 1px solid #bdbaba;
}

.coverage-line {
  display: flex;
  align-items: center;
  padding-left: 5px;

  .coverage-status {
    display: inline-block;
    width: 30px;
    min-width: 30px;
    text-align: center;
  }

  .coverage-line-number {
    min-width: 50px;
    text-align: right;
    padding-right: 10px;
    padding-left: 10px;
    color: #4e524e;
    font-weight: bold;
    position: absolute;
    right: 0;
  }
}
</style>

