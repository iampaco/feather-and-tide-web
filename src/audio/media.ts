const directory = `${import.meta.env.BASE_URL}assets/media/`;

export const landingMusic = `${directory}feather-and-tide-landing.mp3`;

export const soundtrack = {
  theme: `${directory}feather-and-tide.mp3`,
  goose: `${directory}plateau-at-dusk.mp3`,
  whale: `${directory}deep-blue-drones.mp3`,
} as const;
