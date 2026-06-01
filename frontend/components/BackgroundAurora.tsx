export function BackgroundAurora() {
  return (
    <div aria-hidden className="fixed inset-0 -z-0 overflow-hidden">
      <div className="aurora-one absolute -top-1/3 left-1/2 h-[760px] w-[760px] -translate-x-1/2 rounded-full blur-3xl animate-aurora" />
      <div className="aurora-two absolute top-1/3 -right-40 h-[560px] w-[560px] rounded-full blur-3xl animate-aurora-slow" />
      <div className="aurora-three absolute -bottom-40 -left-40 h-[560px] w-[560px] rounded-full blur-3xl animate-aurora-drift" />
      <div className="aurora-four absolute top-1/2 left-1/4 h-[380px] w-[380px] rounded-full blur-3xl animate-aurora-slow" />
      <div className="absolute inset-0 grid-bg" />
      <div className="aurora-fade absolute inset-0" />
    </div>
  );
}
