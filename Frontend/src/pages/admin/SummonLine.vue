<template>
  <tr
    class="is-size-7"
  >
    <td>
      {{ page*10 + index }}-
      <a :href="'https://gbf.wiki/' + item.nameen" target="_blank">
        {{ item.nameen }}
      </a><br>
      {{ item.starsmax }}*<br>
      <label class="checkbox"><input type="checkbox" v-model="item.ignore" tabindex="-1"> Ignore</label>
    </td>
    <td>
      <div v-for="aura in [{name: 'aura', index: 0}, {name: 'auramlb', index: 3}, {name: 'auraflb', index: 4}, {name: 'auraulb', index: 5}, ]" :key="aura.index">
        <span v-if="item[aura.name] !== null">
          <span class="field is-grouped has-no-margin">
            <button class="button is-small is-dark" tabindex="-1" @click="addProp(aura.index)">+</button>
            <button class="button is-small is-dark" tabindex="-1" @click="removeProp(aura.index)">-</button>
            <span>
              {{ aura.index }}: {{ item[aura.name] }}
              <span v-if="item['sub' + aura.name] !== null"><br>{{ aura.index }}s: {{ item['sub' + aura.name] }}</span>
            </span>
          </span>
          <span v-if="item.data">
            <summon-props v-for="(d, i) in item.data[aura.index]" :key="i" :object="d"></summon-props>
          </span>
        </span>
      </div>
    </td>
    <td>            
      <textarea
        class="textarea is-small has-background-dark has-text-grey-light"
        spellcheck="false"
        style="width: 80ch; font-family: monospace;"
        v-model.lazy="getObjectJSON"
      ></textarea>
    </td>          
  </tr>
</template>

<script>
import SummonProps from './SummonProps.vue'

export default {
  components: {
    SummonProps,
  },
  props: {
    item: {
      type: Object,
      required: true
    },
    index: {
      type: Number,
      required: true
    },
    page: {
      type: Number,
      required: true
    }
  },
  methods: {
    addProp(stars) {
      if ( ! this.item.data) {
        Vue.set(this.item, 'data', {});
      }
      if ( ! this.item.data.hasOwnProperty(stars)) {
        Vue.set(this.item.data, stars, []);
      }
      this.item.data[stars].push({});
    },
    removeProp(stars) {
      if (this.item.data) {
        this.item.data[stars].pop();
        if (this.item.data[stars].length === 0) {
          Vue.delete(this.item.data, stars);
        }      
        if (Object.keys(this.item.data).length === 0) {
          Vue.delete(this.item, 'data');
        }
      }
    },
  },
  computed: {
    getObjectJSON: {
      get() {
        return JSON.stringify(this.item.data);
      },
      set(value) {
        Vue.set(this.item, 'data', {});

        for (let [key, val] of Object.entries(JSON.parse(value))) {
          Vue.set(this.item.data, key, val);
        }
      },
    }, 
  }
}
</script>

<style>

.has-no-margin {
  margin-bottom: 0 !important;
}

</style>