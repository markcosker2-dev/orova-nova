export default class ProceduralAssets {
    static createDolphin(scene) {
        const graphics = scene.make.graphics({ x: 0, y: 0, add: false });
        // Body (Simplified sleek dolphin shape)
        graphics.fillStyle(0x74b9ff, 1);
        graphics.fillEllipse(64, 64, 100, 50);
        // Tail
        graphics.fillTriangle(10, 50, 10, 78, 30, 64);
        // Fin
        graphics.fillTriangle(60, 40, 80, 40, 70, 20);
        // Eye
        graphics.fillStyle(0x2d3436, 1);
        graphics.fillCircle(100, 55, 4);

        graphics.generateTexture('dolphin_new', 128, 128);
    }

    static createKitchenItems(scene) {
        // Flour
        let g = scene.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0xffffff, 1);
        g.fillRoundedRect(16, 16, 96, 96, 20);
        g.lineStyle(4, 0xbdc3c7);
        g.strokeRoundedRect(16, 16, 96, 96, 20);
        g.generateTexture('item_flour', 128, 128);

        // Sugar (Pink bowl)
        g = scene.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0xfd79a8, 1);
        g.fillEllipse(64, 80, 100, 60);
        g.fillStyle(0xffffff, 1);
        g.fillEllipse(64, 50, 80, 40);
        g.generateTexture('item_sugar', 128, 128);

        // Butter
        g = scene.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0xffe66d, 1);
        g.fillRect(16, 40, 96, 48);
        g.lineStyle(2, 0x2d3436);
        g.strokeRect(16, 40, 96, 48);
        g.generateTexture('item_butter', 128, 128);

        // Blueberries
        g = scene.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0x0984e3, 1);
        for(let i=0; i<10; i++) {
            g.fillCircle(40 + (i%3)*25, 40 + (i/3)*25, 12);
        }
        g.generateTexture('item_blueberries', 128, 128);
    }

    static createBlocks(scene) {
        const colors = [0x6c5ce7, 0xa29bfe, 0xfd79a8];
        const icons = ['❤️', '💋', '💍'];
        
        colors.forEach((color, i) => {
            const g = scene.make.graphics({ x: 0, y: 0, add: false });
            g.fillStyle(color, 1);
            g.fillRoundedRect(10, 10, 108, 108, 15);
            g.lineStyle(4, 0xffffff, 0.5);
            g.strokeRoundedRect(10, 10, 108, 108, 15);
            g.generateTexture(`block_${i}`, 128, 128);
        });
    }

    static createHearts(scene) {
        const g = scene.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0xff7675, 1);
        // Simplified Heart
        g.fillCircle(44, 44, 30);
        g.fillCircle(84, 44, 30);
        g.fillTriangle(14, 44, 114, 44, 64, 114);
        g.generateTexture('heart_new', 128, 128);
    }
}
