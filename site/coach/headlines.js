/* Coach's take headlines. EDIT ME: the first entry whose `when` is true wins, so order matters.
   `s` is { total, fixTeams, byeTeams }: how many lineups there are, how many have something to
   fix, and how many have a starter on bye. `{n}` in `text` becomes the number of lineups to fix. */
const COACH_HEADLINES = [
  { when: (s) => s.byeTeams >= 4, text: 'Bye week came for everyone.' },
  { when: (s) => s.fixTeams <= 1, text: 'Mostly fine, and Coach is suspicious.' },
  { when: (s) => s.fixTeams <= 3, text: 'A few lineups need a hug and a swap.' },
  { when: () => true, text: 'Coach has notes.' },
];
if (typeof module !== 'undefined') module.exports = { COACH_HEADLINES };
