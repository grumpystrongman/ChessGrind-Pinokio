module.exports = {
  version: "3.1",
  title: "Chess Grind",
  description: "A local-first chess school: play, analyze your games, master openings, and study historic masters.",
  icon: "icons/icon-192.png",
  menu: async (kernel, info) => {
    const installed = info.exists(".venv/pyvenv.cfg");
    if (info.running("install.js"))
      return [{default:true, icon:"fa-solid fa-download", text:"Installing Chess Grind", href:"install.js"}];
    if (!installed)
      return [{default:true, icon:"fa-solid fa-download", text:"Install Chess Grind", href:"install.js"}];
    if (info.running("start.js")) {
      const instance = info.local("start.js");
      return [
        ...(instance && instance.url ? [{default:true, icon:"fa-solid fa-chess-board", text:"Open Chess Grind", href:instance.url}] : []),
        {icon:"fa-solid fa-terminal", text:"Server log / Stop", href:"start.js"}
      ];
    }
    return [
      {default:true, icon:"fa-solid fa-play", text:"Start Chess Grind", href:"start.js"},
      {icon:"fa-solid fa-stethoscope", text:"Check installation", href:"doctor.js"},
      {icon:"fa-solid fa-volume-high", text:"Install optional neural coach voices", href:"install-voices.js"},
      {icon:"fa-solid fa-wrench", text:"Repair dependencies", href:"install.js"},
      {icon:"fa-solid fa-rotate", text:"Update application (preserves games)", href:"update.js"}
    ];
  }
};

