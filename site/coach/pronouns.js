/* Coach writes to the team's own manager ("your bench", "you're set"). On someone else's team the
   same sentence has to say "her bench", "she's set". This swaps the second person for the third,
   word by word, for the copy the build and coach-daily write. A "you" that opens a clause (start of
   the line, after punctuation, or after a word like "if", "so", "than") is the subject: it becomes
   "she" and the verb after it is conjugated ("you roster" → "she rosters"). Any other "you" is an
   object ("lost you points", "has you projected") and becomes "her". A line with no second person
   comes back exactly as it went in. */
const HER_IRREGULAR = { are: 'is', were: 'was', have: 'has', do: 'does', go: 'goes', "don't": "doesn't",
  "haven't": "hasn't", "aren't": "isn't", "weren't": "wasn't" };
// Words after a subject "you" that stay as they are: modals, and past tenses that don't end in -ed.
const HER_KEEP = new Set(('can cannot could will would should might must may shall did had was got made took sat kept left lost '
  + 'won held ran gave saw knew went drew chose sent spent found told thought brought bought paid said felt came became '
  + 'heard began stood wrote fell forgot caught taught meant built dealt threw grew wore drove broke spoke woke ate tore '
  + 'stuck sold rode led stole swung sank slept hung better ought is').split(' '));
// Present tenses that end in -ed or -ing, which would otherwise read as a past tense or a gerund.
const HER_ED = /^(need|feed|succeed|proceed|exceed|bleed|speed|breed|embed|shed)$/;
const HER_ING = /^(bring|swing|sting|sing|ring|cling|spring|fling|wring)$/;
// Adverbs that can sit between "you" and its verb ("you still need" → "she still needs").
const HER_ADVERB = 'still|also|just|only|never|always|really|probably|already|actually|even|ever|likely|quietly|clearly|usually|often|rarely|then|now|basically|somehow|no longer|kind of|sort of';
// Words after which "you" starts a clause, so it's the subject ("if you start", "than you do").
const HER_SUBJECT_AFTER = new Set(('if when whenever so and but or because unless before after until while since that what '
  + 'where which who whether once as than though although like now then says say said means mean meant thinks think '
  + 'guess bet hope knows know suggests figures sure').split(' '));
// Words after which "you" is the object ("lost you points", "has you projected", "carried you past"):
// prepositions, any -ing verb ("telling you to"), and the verbs Coach puts "you" after. After any other word (a noun, as in "the only
// quarterback you roster") it is the subject.
const HER_OBJECT_AFTER = new Set(('at for to of with from on about without against behind past into onto over under above '
  + 'below around through by toward towards near beside between among per '
  + 'has have had lost lose loses gives give gave carried carry carries drops drop dropped stop stops stopped cost costs '
  + 'leaves leave left puts put makes make made gets get got keeps keep kept tells tell told shows show showed lets let '
  + 'beat beats helps help helped owes owe saves save saved sends send sent offers offer offered pays pay paid likes '
  + 'pairs paired wants needs lifts lifted sinks sank hurts hurt burned burns bails bailed buys buy bought earned earns '
  + 'handed hands takes take took loves hates picks picked ranks ranked rates rated favors favored projects projected '
  + 'pegs pegged sees see saw catch catches caught robbed robs warns warned reminds remind reminded thank thanks ask '
  + 'asks asked miss misses missed cheat cheats cheated beats put sets moves moved costing giving leaving'
  ).split(' '));
// Words that can't be the verb of a subject "you" ("you and Amie", "you both").
const HER_NOT_VERB = new Set(('and or but nor both all a an the to in on at for of with by from into onto over off out up '
  + 'down back again this that these those if as than so too here there more less').split(' '));
// A second verb sharing the same subject across "and"/"or" ("you roster eight and start three" →
// "she rosters eight and starts three"). Deliberately conservative: a miss leaves the bare verb,
// which only reads a little off, while a false hit changes what the card claims ("shouldn't panic
// and drop him" → "and drops him"). The guards below cost some real conjugations; the tests pin
// both what it fixes and what it knowingly leaves alone.
// `cut`, `set` and `read` are left out on purpose: their past tense is spelled the same, so
// "she added Gibbs and cut Waddle" is indistinguishable from a present-tense compound.
const HER_COMPOUND = new Set(('start sit bench play roster own carry keep hold need want hope lose win get have take '
  + 'leave trust claim grab add drop trade swap stream ride check watch run score miss pick move wait hand '
  + 'give send rest fix stash stack chase cover').split(' '));
// A modal, a negated modal or an infinitive between the subject and the conjunction governs the
// whole compound, so the second verb stays bare ("she can start him and keep the flex", "she needs
// to start him and keep the flex", "she shouldn't panic and drop him"). The `n't` alternative is
// separate because there is no word boundary inside "shouldn't" for `\bshould\b` to match.
const HER_GOVERNS = /\b(can|could|will|would|should|might|must|may|shall|do|does|did|to)\b|n[’']t\b|\bcannot\b/i;
// Fixed phrases where "and" joins two nouns that are also on the verb list ("her start and sit
// calls"). Listed by name rather than inferred, because the general shape is indistinguishable from
// a real compound ("left on the bench and need a flex" has a noun-list word before "and" too).
const HER_NOUN_PAIRS = /\b(start and sit|sit and start|add and drop|drop and add|buy and hold|claim and pick|set and forget)\b/i;
// Periods that do not end a sentence: decimals ("14.2") and the abbreviations in these names.
// Replacements keep the original length so string offsets still line up.
const herSentence = (before) => {
  const masked = before
    .replace(/(\d)\.(\d)/g, '$1_$2')
    .replace(/\b(St|Jr|Sr|Mr|Ms|Dr|vs)\./gi, (s) => `${s.slice(0, -1)}_`)
    .replace(/\b([A-Za-z])\./g, '$1_');
  return before.slice(masked.search(/[^.;:!?]*$/));
};

const herNorm = (w) => w.toLowerCase().replace(/’/g, "'");

// "roster" → "rosters", "miss" → "misses", "carry" → "carries", "are" → "is", "don’t" → "doesn’t".
function herVerb(v) {
  const low = herNorm(v);
  if (HER_IRREGULAR[low]) return v.includes('’') ? HER_IRREGULAR[low].replace(/'/g, '’') : HER_IRREGULAR[low];
  if (HER_KEEP.has(low) || /n't$/.test(low)) return v;
  if (/ed$/.test(low) && !HER_ED.test(low)) return v;
  if (/(s|x|z|ch|sh|o)$/.test(low)) return `${v}es`;
  if (/[^aeiou]y$/.test(low)) return `${v.slice(0, -1)}ies`;
  return `${v}s`;
}

function herCopy(text) {
  if (typeof text !== 'string' || !text) return text;
  const cap = (from, to) => (from[0] === from[0].toUpperCase() ? to[0].toUpperCase() + to.slice(1) : to);
  return text
    .replace(/\b(you)(['’])(re|ve|ll|d)\b/gi, (m, y, a, c) => cap(y, 'she') + a + (/^(re|ve)$/i.test(c) ? 's' : c.toLowerCase()))
    .replace(/\byourself\b/gi, (m) => cap(m, 'herself'))
    .replace(/\byours\b/gi, (m) => cap(m, 'hers'))
    .replace(/\byour\b/gi, (m) => cap(m, 'her'))
    .replace(new RegExp(`\\b(you)\\b((?:\\s+(?:${HER_ADVERB})\\b)*)(?:(\\s+)([a-z][a-z'’-]*))?`, 'gi'), (m, y, adv, sp, w, at, all) => {
      const prev = (all.slice(0, at).match(/([A-Za-z'’]+)\s*$/) || [])[1];
      const pl = prev && prev.toLowerCase();
      const subject = !pl || HER_SUBJECT_AFTER.has(pl) || !(HER_OBJECT_AFTER.has(pl) || /ing$/.test(pl));
      const tail = `${adv}${sp || ''}${w || ''}`;
      // An object, a "you" with nothing after it ("than you."), or a gerund ("You starting him"): "her".
      if (!subject || !w || /^[A-Z]/.test(w) || (!adv && /ing$/i.test(w) && !HER_ING.test(w.toLowerCase()))) return cap(y, 'her') + tail;
      if (!adv && HER_NOT_VERB.has(w.toLowerCase())) return cap(y, 'she') + tail;
      return `${cap(y, 'she')}${adv}${sp}${herVerb(w)}`;
    })
    // Runs last, on the already-converted text: a bare second verb after "and"/"or" that shares the
    // subject with a "she" earlier in the same sentence.
    .replace(/\b(and|or)(\s+)([a-z][a-z'’-]*)/gi, (m, conj, sp, w, at, all) => {
      if (!HER_COMPOUND.has(herNorm(w))) return m;
      const sentence = herSentence(all.slice(0, at));
      const subject = sentence.search(/\bshe\b/i);
      if (subject === -1) return m;
      const span = sentence.slice(subject);              // subject up to the conjunction
      if (HER_GOVERNS.test(span)) return m;
      // A comma starts a new clause, so the conjunction may join an imperative ("she is thin at
      // receiver, and check Friday's report") or a comma series, neither of which agrees with "she".
      if (span.includes(',')) return m;
      const prev = (sentence.match(/([A-Za-z'’]+)\s*$/) || [])[1];
      if (prev && HER_NOUN_PAIRS.test(`${prev} ${conj} ${w}`)) return m;
      return `${conj}${sp}${herVerb(w)}`;
    });
}
if (typeof module !== 'undefined') module.exports = { herCopy };
