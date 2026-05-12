export default class Level3 extends Phaser.Scene {
    constructor() {
        super('Level3');
    }

    preload() {
        this.load.image('tile', 'assets/tile.png');
        this.load.svg('dolphin', 'assets/dolphin.svg');
        this.load.svg('heart', 'assets/heart.svg');
    }

    create() {
        const bg = this.add.tileSprite(400, 300, 800, 600, 'tile');
        bg.setTint(0x99ff99).setAlpha(0.6); // Tinted green for garden

        this.player = this.physics.add.sprite(400, 300, 'dolphin');
        this.player.setCollideWorldBounds(true);
        this.player.setScale(0.8);

        // Pedestals
        this.pedestals = this.physics.add.staticGroup();
        const locations = [200, 400, 600];
        locations.forEach(x => {
            this.pedestals.create(x, 200, 'heart').setScale(0.5).setAlpha(0.2).setTint(0x000000);
        });

        // Hidden Hearts
        this.items = this.physics.add.group();
        this.items.create(100, 500, 'heart').setScale(0.6);
        this.items.create(400, 500, 'heart').setScale(0.6);
        this.items.create(700, 500, 'heart').setScale(0.6);

        // Gate Overlay (Ornate)
        this.gateGraphics = this.add.graphics();
        this.gateGraphics.lineStyle(10, 0xffd700, 1);
        this.gateGraphics.strokeRect(200, 0, 400, 60);
        this.gateGraphics.setAlpha(0);

        this.cursors = this.input.keyboard.createCursorKeys();
        this.collected = 0;

        this.physics.add.overlap(this.player, this.items, (p, item) => {
            item.disableBody(true, true);
            this.collected++;
            const ped = this.pedestals.getChildren()[this.collected - 1];
            ped.setAlpha(1).clearTint();

            if (this.collected === 3) {
                this.win();
            }
        });

        this.cameras.main.fadeIn(1000);
        this.events.emit('show-dialogue', "Level 3: The Heart Pedestals\nFind the 3 golden hearts to open the gate.");
    }

    update() {
        this.player.setVelocity(0);
        const speed = 200;
        if (this.cursors.left.isDown) this.player.setVelocityX(-speed);
        else if (this.cursors.right.isDown) this.player.setVelocityX(speed);
        if (this.cursors.up.isDown) this.player.setVelocityY(-speed);
        else if (this.cursors.down.isDown) this.player.setVelocityY(speed);
    }

    win() {
        this.tweens.add({
            targets: this.gateGraphics,
            alpha: 1,
            y: 50,
            duration: 2000,
            onComplete: () => {
                this.events.emit('show-dialogue', "Congratulations!\nYou found all the hearts.\n\nAsk Mark for the prize. ❤️");
            }
        });
    }
}
