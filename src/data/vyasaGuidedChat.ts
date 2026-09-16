// Vyasa's guided chat menu — every question here maps to a category the
// backend can genuinely answer today (see app/services/interpretation/
// templates.py: the dynamic timing/decision categories, plus the static
// natal-placement topics under _TOPIC_KEYWORDS, plus dosha/yoga/today/
// year_ahead). Exact phrasing matters — each one was verified live against
// the real chat endpoint before being added here, since the backend routes
// purely on keyword/phrase matching, not intent understanding.
export interface VyasaCategory {
  key: string;
  labelKey: string;
  questionKeys: string[];
}

export const VYASA_CATEGORIES: VyasaCategory[] = [
  {
    key: 'marriage',
    labelKey: 'rishi.testCategoryMarriage',
    questionKeys: [
      'rishi.promptMarriageFuture',
      'rishi.promptMarriagePast',
      'rishi.promptMarriageGeneral',
      'rishi.promptManglik',
    ],
  },
  {
    key: 'career',
    labelKey: 'rishi.testCategoryCareer',
    questionKeys: ['rishi.promptCareerGrowth', 'rishi.promptCareerPromotion', 'rishi.promptCareerGeneral'],
  },
  {
    key: 'business',
    labelKey: 'rishi.testCategoryBusiness',
    questionKeys: ['rishi.promptBusinessExpansion', 'rishi.promptBusinessPartner'],
  },
  {
    key: 'wealth',
    labelKey: 'rishi.testCategoryWealth',
    questionKeys: ['rishi.promptWealthGrowth', 'rishi.promptMoneyGeneral'],
  },
  {
    key: 'family',
    labelKey: 'rishi.testCategoryFamily',
    questionKeys: ['rishi.promptFamilyChildren', 'rishi.promptFamilyGeneral'],
  },
  {
    key: 'foreignTravel',
    labelKey: 'rishi.testCategoryForeignTravel',
    questionKeys: ['rishi.promptForeignTravelStrongest', 'rishi.promptTravelGeneral'],
  },
  {
    key: 'health',
    labelKey: 'rishi.categoryHealth',
    questionKeys: ['rishi.promptHealthGeneral'],
  },
  {
    key: 'education',
    labelKey: 'rishi.categoryEducation',
    questionKeys: ['rishi.promptEducationGeneral'],
  },
  {
    key: 'doshaYoga',
    labelKey: 'rishi.categoryDoshaYoga',
    questionKeys: ['rishi.promptDoshaGeneral', 'rishi.promptYogaGeneral'],
  },
  {
    key: 'todayYear',
    labelKey: 'rishi.categoryTodayYear',
    questionKeys: ['rishi.promptTodayGeneral', 'rishi.promptYearAheadGeneral'],
  },
  {
    key: 'decisions',
    labelKey: 'rishi.testCategoryDecisions',
    questionKeys: ['rishi.promptJobChangeDecision', 'rishi.promptBusinessStartDecision'],
  },
];
