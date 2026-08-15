import { defineComponents } from "blume";

import SynthFooter from "./components/SynthFooter.astro";
import Header from "./components/blume/Header.astro";

export default defineComponents({
  layout: {
    Footer: SynthFooter,
    Header,
  },
});
