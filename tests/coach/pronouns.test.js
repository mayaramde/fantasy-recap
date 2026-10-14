const test = require('node:test');
const assert = require('node:assert/strict');
const { herCopy } = require('../../site/coach/pronouns.js');

test('possessives and contractions go third person', () => {
  assert.equal(herCopy('Your bench is quietly outprojecting your lineup.'), 'Her bench is quietly outprojecting her lineup.');
  assert.equal(herCopy("You're set. You've earned it."), "She's set. She's earned it.");
  assert.equal(herCopy('Nobody on your bench plays RB.'), 'Nobody on her bench plays RB.');
});

test('"you" is her as an object and she as a subject, with the verb to match', () => {
  assert.equal(herCopy('Look at you.'), 'Look at her.');
  assert.equal(herCopy('That is exactly where you want your zeroes.'), 'That is exactly where she wants her zeroes.');
  assert.equal(herCopy('You have a swap. You are fine.'), 'She has a swap. She is fine.');
  assert.equal(herCopy('ESPN says you should start him.'), 'ESPN says she should start him.');
});

test('copy with no second person, and non-strings, pass through untouched', () => {
  assert.equal(herCopy('Amie benched 14.2 points.'), 'Amie benched 14.2 points.');
  assert.equal(herCopy('Layout youthful'), 'Layout youthful');
  assert.equal(herCopy(''), '');
  assert.equal(herCopy(undefined), undefined);
});
